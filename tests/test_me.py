"""Tests for the ``/api/v1/me`` endpoint."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core.dummy_user import DUMMY_USER_ID, DUMMY_USER_NAME
from app.repositories.users import SQLUserRepository

PATH = "/api/v1/me"
# Created before the dummy user, with an id that sorts before theirs, so an
# endpoint returning the first user it finds would return this one instead.
OTHER_USER_ID = UUID("00000000-0000-7000-8000-000000000000")


@pytest.fixture
def dummy_user(connection: Connection) -> None:
    user_repo = SQLUserRepository(connection)
    user_repo.create(OTHER_USER_ID, "Other user")
    user_repo.create(DUMMY_USER_ID, DUMMY_USER_NAME)


@pytest.mark.usefixtures("dummy_user")
def test_returns_the_dummy_user(client: TestClient) -> None:
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json() == {"id": str(DUMMY_USER_ID), "name": DUMMY_USER_NAME}


def test_is_forbidden_without_the_dummy_user(client: TestClient) -> None:
    response = client.get(PATH)
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorised"}


def test_is_documented_with_its_responses(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"][PATH]["get"]
    success = operation["responses"]["200"]["content"]["application/json"]
    assert success["schema"] == {"$ref": "#/components/schemas/UserResponse"}
    forbidden = operation["responses"]["403"]
    assert forbidden["description"] == "The current user is not authorised"
