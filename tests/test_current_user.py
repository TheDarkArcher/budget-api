"""Tests for the current-user resolver in front of every ``/api/v1`` request."""

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.api import dependencies, v1
from app.api.dependencies import CurrentUserDep
from app.core.dummy_user import DUMMY_USER_ID, DUMMY_USER_NAME
from app.database.engine import get_connection
from app.main import create_app
from app.repositories.users import SQLUserRepository, User, UserRepository
from app.services.users import get_user


def open_endpoint() -> dict[str, bool]:
    return {"ok": True}


def whoami(user: CurrentUserDep) -> dict[str, str]:
    return {"id": str(user.id), "name": user.name}


@pytest.fixture
def probe_client(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    # Probe routes on the real v1 router, added to a copy of its routes that
    # monkeypatch swaps back after the test.
    monkeypatch.setattr(v1.router, "routes", list(v1.router.routes))
    v1.router.add_api_route("/test/open", open_endpoint)
    v1.router.add_api_route("/test/whoami", whoami)
    app = create_app()

    # A savepoint per request, as in conftest.py's app fixture.
    def override() -> Iterator[Connection]:
        with connection.begin_nested():
            yield connection

    app.dependency_overrides[get_connection] = override
    with TestClient(app) as client:
        yield client


@pytest.fixture
def dummy_user(connection: Connection) -> None:
    SQLUserRepository(connection).create(DUMMY_USER_ID, DUMMY_USER_NAME)


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

    monkeypatch.setattr(dependencies, "get_user", counting_get_user)
    # The endpoint asks for the user, and the router resolves it as well.
    probe_client.get("/api/v1/test/whoami")
    assert looked_up == [DUMMY_USER_ID]


@pytest.mark.usefixtures("dummy_user")
def test_endpoints_that_dont_ask_for_the_user_still_succeed(
    probe_client: TestClient,
) -> None:
    assert probe_client.get("/api/v1/test/open").status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/test/whoami", "/api/v1/test/open"])
def test_requests_are_forbidden_without_the_dummy_user(
    probe_client: TestClient, caplog: pytest.LogCaptureFixture, path: str
) -> None:
    response = probe_client.get(path)
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorised"}
    assert "has the database been seeded?" in caplog.text


def test_health_endpoints_dont_need_the_dummy_user(probe_client: TestClient) -> None:
    assert probe_client.get("/health/live").status_code == 200
