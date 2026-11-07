"""Health checks for the app and its subsystems."""

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future

from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.core.config import get_settings
from app.database.engine import ping
from app.schemas.health import (
    CheckResult,
    HealthStatus,
    LivenessResponse,
    ReadinessResponse,
)

logger = logging.getLogger(__name__)

type HealthCheck = Callable[[], None]

CHECK_TIMEOUT_SECONDS = 2

HEALTH_CHECKS: dict[str, HealthCheck] = {}

# The run of each check that is still in progress. A check stuck on an
# unresponsive subsystem is never started again until it finishes, so at
# most one thread per check is ever tied up.
_in_flight: dict[str, Future[None]] = {}


class HealthCheckError(Exception):
    """Raised by a check when its subsystem is unhealthy.

    The message is returned to clients, so it must not contain
    connection details or other internals.
    """


def health_check(name: str) -> Callable[[HealthCheck], HealthCheck]:
    """Register a function as a named health check.

    Args:
        name: Key the check's result is reported under.

    Returns:
        A decorator that registers the check and returns it unchanged.
    """

    def register(check: HealthCheck) -> HealthCheck:
        HEALTH_CHECKS[name] = check
        return check

    return register


def _start(name: str, check: HealthCheck) -> Future[None]:
    # A daemon thread, unlike a ThreadPoolExecutor worker, can't stop the
    # process from exiting while it is stuck.
    future: Future[None] = Future()

    def run() -> None:
        future.set_running_or_notify_cancel()
        try:
            check()
        # Not swallowed: the future re-raises it in the awaiting request.
        except BaseException as exc:  # noqa: BLE001
            future.set_exception(exc)
        else:
            future.set_result(None)

    threading.Thread(target=run, name=f"health-check-{name}", daemon=True).start()
    return future


async def run_check(name: str, check: HealthCheck) -> CheckResult:
    """Run one check in its own thread, with a deadline.

    If an earlier run of the same check is still in progress, it is
    reported as timed out without starting another.

    Args:
        name: Name of the check.
        check: The check to run.

    Returns:
        The check's status, latency and, if it failed, a safe error message.
    """
    previous = _in_flight.get(name)
    if previous is not None and not previous.done():
        logger.warning("Health check %r is still running from an earlier request", name)
        return CheckResult(status=HealthStatus.ERROR, error="Timed out")

    future = _in_flight[name] = _start(name, check)
    error: str | None = None
    failure: BaseException | None = None
    start = time.perf_counter()
    try:
        await asyncio.wait_for(asyncio.wrap_future(future), CHECK_TIMEOUT_SECONDS)
    except HealthCheckError as exc:
        error, failure = str(exc), exc
    except TimeoutError:
        error = "Timed out"
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000)
    if error is None:
        return CheckResult(status=HealthStatus.OK, latency_ms=latency_ms)
    logger.warning("Health check %r failed: %s", name, error, exc_info=failure)
    return CheckResult(status=HealthStatus.ERROR, latency_ms=latency_ms, error=error)


def get_liveness() -> LivenessResponse:
    """Report that the app process is up.

    Returns:
        An ``ok`` status, the app version and the build label, if known.
    """
    return LivenessResponse(
        status=HealthStatus.OK, version=__version__, build=get_settings().app_build
    )


async def get_readiness(checks: Mapping[str, HealthCheck]) -> ReadinessResponse:
    """Run every check concurrently and combine the results.

    Args:
        checks: The checks to run, by name.

    Returns:
        The overall readiness, which is ``ok`` only if every check is ``ok``.
    """
    names = list(checks)
    results = await asyncio.gather(*(run_check(name, checks[name]) for name in names))
    healthy = all(result.status is HealthStatus.OK for result in results)
    return ReadinessResponse(
        status=HealthStatus.OK if healthy else HealthStatus.ERROR,
        version=__version__,
        build=get_settings().app_build,
        checks=dict(zip(names, results, strict=True)),
    )


@health_check("database")
def check_database() -> None:
    """Check that the database answers within the timeout.

    Raises:
        HealthCheckError: If the database is unreachable or too slow.
    """
    try:
        ping()
    except SQLAlchemyError as exc:
        raise HealthCheckError("Database unavailable") from exc
