"""Health endpoints.

Both are ``async`` and never block the event loop, so they still answer
when the threadpool that serves other requests is exhausted.
"""

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.schemas.health import HealthStatus, LivenessResponse, ReadinessResponse
from app.services.health import (
    HEALTH_CHECKS,
    HealthCheck,
    get_liveness,
    get_readiness,
)

router = APIRouter(prefix="/health", tags=["health"])


async def get_health_checks() -> Mapping[str, HealthCheck]:
    """Provide the registered health checks.

    Returns:
        The health checks, by name.
    """
    return HEALTH_CHECKS


HealthChecksDep = Annotated[Mapping[str, HealthCheck], Depends(get_health_checks)]


@router.get(
    "/live",
    response_model_exclude_none=True,
    response_description="The app is running",
)
async def live() -> LivenessResponse:
    """Report whether the app process is up, without checking any subsystem.

    Returns:
        An ``ok`` status, the app version and the build label, if known.
    """
    return get_liveness()


@router.get(
    "/ready",
    response_model_exclude_none=True,
    response_description="All subsystems are healthy",
    responses={
        503: {"model": ReadinessResponse, "description": "A subsystem is unhealthy"}
    },
)
async def ready(checks: HealthChecksDep, response: Response) -> ReadinessResponse:
    """Report whether the app and each subsystem it depends on are ready.

    Args:
        checks: The health checks to run.
        response: The outgoing response, used to set 503 when not ready.

    Returns:
        The overall readiness and each check's result.
    """
    result = await get_readiness(checks)
    if result.status is not HealthStatus.OK:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
