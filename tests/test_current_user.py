"""Tests for the current-user resolver in front of every versioned API request."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from problems import assert_problem
from sql import count
from sqlalchemy import Connection

from app.api import current_user, v1
from app.api.dependencies import ConnectionDep, CurrentUserDep
from app.core.config import get_settings
from app.core.dummy_user import DUMMY_USER_ID, DUMMY_USER_NAME
from app.core.errors import ArchivedError
from app.main import create_app
from app.repositories.users import SQLUserRepository, User, UserRepository
from app.services.users import get_user

ORIGIN = "http://frontend.test"
WRITTEN_USER_ID = UUID("00000000-0000-7000-8000-0000000000c1")


def open_endpoint() -> dict[str, bool]:
    return {"ok": True}


def whoami(user: CurrentUserDep) -> dict[str, str]:
    return {"id": str(user.id), "name": user.name}


def write_then_refuse(connection: ConnectionDep) -> None:
    SQLUserRepository(connection).create(WRITTEN_USER_ID, "Written")
    raise ArchivedError


@pytest.fixture
def probe_client(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    # Probe routes on the real v1 router, added to a copy of its routes that
    # monkeypatch swaps back after the test.
    monkeypatch.setattr(v1.router, "routes", list(v1.router.routes))
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ORIGIN)
    get_settings.cache_clear()
    v1.router.add_api_route("/test/open", open_endpoint)
    v1.router.add_api_route("/test/whoami", whoami)
    v1.router.add_api_route(
        "/test/write-then-refuse", write_then_refuse, methods=["POST"]
    )

    # A savepoint per request, as in conftest.py's app fixture.
    @contextmanager
    def open_savepoint() -> Generator[Connection]:
        with connection.begin_nested():
            yield connection

    with TestClient(create_app(open_connection=open_savepoint)) as client:
        yield client
    get_settings.cache_clear()


@pytest.mark.usefixtures("dummy_user")
def test_requests_act_as_the_dummy_user(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/test/whoami")
    assert response.status_code == 200
    assert response.json() == {"id": str(DUMMY_USER_ID), "name": DUMMY_USER_NAME}


@pytest.mark.usefixtures("dummy_user")
def test_the_user_is_looked_up_once_per_request(
    probe_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    looked_up: list[UUID] = []

    def counting_get_user(user_repo: UserRepository, user_id: UUID) -> User | None:
        looked_up.append(user_id)
        return get_user(user_repo, user_id)

    monkeypatch.setattr(current_user, "get_user", counting_get_user)
    # The endpoint asks for the user, and the resolver has already found it.
    probe_client.get("/api/v1/test/whoami")
    assert looked_up == [DUMMY_USER_ID]


@pytest.mark.usefixtures("dummy_user")
def test_endpoints_that_dont_ask_for_the_user_still_succeed(
    probe_client: TestClient,
) -> None:
    assert probe_client.get("/api/v1/test/open").status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        pytest.param("GET", "/api/v1/test/whoami", id="asks-for-user"),
        pytest.param("GET", "/api/v1/test/open", id="doesnt-ask-for-user"),
        pytest.param("GET", "/api/v1/test/unknown", id="unknown-path"),
        pytest.param("DELETE", "/api/v1/test/open", id="unsupported-method"),
        pytest.param("GET", "/api/v2/test/open", id="later-version"),
    ],
)
def test_requests_are_forbidden_without_the_dummy_user(
    probe_client: TestClient, caplog: pytest.LogCaptureFixture, method: str, path: str
) -> None:
    response = probe_client.request(method, path)
    problem_body = assert_problem(response, 403)
    assert problem_body == {
        "type": "about:blank",
        "title": "Forbidden",
        "status": 403,
        "detail": "Not authorised",
    }
    assert "has the database been seeded?" in caplog.text


@pytest.mark.usefixtures("dummy_user")
def test_a_refused_request_keeps_none_of_its_writes(
    probe_client: TestClient, connection: Connection
) -> None:
    response = probe_client.post("/api/v1/test/write-then-refuse")
    assert_problem(response, 409)
    written = count(
        connection, "SELECT count(*) FROM users WHERE id = :id", id=WRITTEN_USER_ID
    )
    assert written == 0


def test_forbidden_problem_carries_cors_headers(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/test/open", headers={"Origin": ORIGIN})
    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_health_endpoints_dont_need_the_dummy_user(probe_client: TestClient) -> None:
    assert probe_client.get("/health/live").status_code == 200


def test_unversioned_api_paths_dont_need_the_dummy_user(
    probe_client: TestClient,
) -> None:
    response = probe_client.get("/api/test/unknown")
    problem_body = assert_problem(response, 404)
    assert problem_body == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
    }
