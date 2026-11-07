"""Tests for the health endpoints."""

import threading
import time
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.api.health import get_health_checks
from app.core.config import get_settings
from app.database.engine import get_ping_engine
from app.services import health
from app.services.health import HealthCheck, HealthCheckError

TIMEOUT_SECONDS = 0.2


def use_checks(app: FastAPI, checks: dict[str, HealthCheck]) -> None:
    async def override() -> dict[str, HealthCheck]:
        return checks

    app.dependency_overrides[get_health_checks] = override


def check_threads(name: str) -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == f"health-check-{name}"]


@pytest.fixture(autouse=True)
def no_checks_in_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    # Each test starts with no runs left over from earlier tests.
    monkeypatch.setattr(health, "_in_flight", {})


@pytest.fixture
def database_down() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", "postgresql://user:secret@127.0.0.1:1/budget")
        get_settings.cache_clear()
        get_ping_engine.cache_clear()
        yield
    get_settings.cache_clear()
    get_ping_engine.cache_clear()


@pytest.fixture
def build() -> Iterator[str]:
    label = "0.2.0-dev.47+1a2b3c4"
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("APP_BUILD", label)
        get_settings.cache_clear()
        yield label
    get_settings.cache_clear()


@pytest.fixture
def no_build() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("APP_BUILD", raising=False)
        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture
def short_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "CHECK_TIMEOUT_SECONDS", TIMEOUT_SECONDS)


@pytest.fixture
def release() -> Iterator[threading.Event]:
    event = threading.Event()
    yield event
    event.set()


@pytest.mark.usefixtures("no_build")
def test_live(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


@pytest.mark.usefixtures("database_down")
def test_live_when_database_is_down(client: TestClient) -> None:
    assert client.get("/health/live").status_code == 200


def test_health_reports_build_label_when_set(client: TestClient, build: str) -> None:
    assert client.get("/health/live").json()["build"] == build
    assert client.get("/health/ready").json()["build"] == build


@pytest.mark.usefixtures("no_build")
def test_health_omits_build_label_when_unset(client: TestClient) -> None:
    assert "build" not in client.get("/health/live").json()
    assert "build" not in client.get("/health/ready").json()


def test_ready_when_database_is_up(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert isinstance(body["checks"]["database"]["latencyMs"], int)
    assert "error" not in body["checks"]["database"]


@pytest.mark.usefixtures("database_down")
def test_ready_when_database_is_down(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["version"] == __version__
    database = body["checks"]["database"]
    assert database["status"] == "error"
    assert database["error"] == "Database unavailable"
    assert "secret" not in response.text
    assert "127.0.0.1" not in response.text


def test_ready_reports_each_check_when_one_fails(
    app: FastAPI, client: TestClient
) -> None:
    def fails() -> None:
        raise HealthCheckError("Cache unavailable")

    use_checks(app, {"passes": lambda: None, "fails": fails})
    response = client.get("/health/ready")
    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks["passes"]["status"] == "ok"
    assert checks["fails"]["status"] == "error"
    assert checks["fails"]["error"] == "Cache unavailable"


@pytest.mark.usefixtures("short_timeout")
def test_ready_when_check_hangs(
    app: FastAPI, client: TestClient, release: threading.Event
) -> None:
    def hangs() -> None:
        release.wait()

    use_checks(app, {"hangs": hangs})

    start = time.perf_counter()
    response = client.get("/health/ready")
    assert time.perf_counter() - start < TIMEOUT_SECONDS + 0.5
    assert response.status_code == 503
    assert response.json()["checks"]["hangs"]["error"] == "Timed out"
    assert len(check_threads("hangs")) == 1

    start = time.perf_counter()
    response = client.get("/health/ready")
    assert time.perf_counter() - start < TIMEOUT_SECONDS
    assert response.status_code == 503
    assert response.json()["checks"]["hangs"]["error"] == "Timed out"
    assert len(check_threads("hangs")) == 1

    release.set()
    for thread in check_threads("hangs"):
        thread.join(timeout=1)
    assert client.get("/health/ready").status_code == 200


def test_ready_runs_checks_concurrently(app: FastAPI, client: TestClient) -> None:
    # Each check waits for the other to start, so run one at a time they
    # would break the barrier and fail the request.
    barrier = threading.Barrier(2, timeout=1)

    def meets_the_other() -> None:
        barrier.wait()

    use_checks(app, {"a": meets_the_other, "b": meets_the_other})
    assert client.get("/health/ready").status_code == 200


def test_unexpected_error_in_a_check_is_not_hidden(
    app: FastAPI, client: TestClient
) -> None:
    def broken() -> None:
        raise RuntimeError("bug in the check")

    use_checks(app, {"broken": broken})
    with pytest.raises(RuntimeError, match="bug in the check"):
        client.get("/health/ready")
