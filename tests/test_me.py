"""Tests for the ``/api/v1/me`` endpoint."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from problems import FORBIDDEN_PROBLEM, assert_problem
from sqlalchemy import Connection

from app.core.dummy_user import DUMMY_USER_ID, DUMMY_USER_NAME
from app.repositories.users import SQLUserRepository

PATH = "/api/v1/me"
# Sorts before the dummy user's id.
OTHER_USER_ID = UUID("00000000-0000-7000-8000-000000000000")


@pytest.fixture
def other_user(connection: Connection) -> None:
    SQLUserRepository(connection).create(OTHER_USER_ID, "Other user")


# The fixtures have been ordered to create the other_user before the dummy
# user so that if the result returned is the first created or the first id
# the other_user is returned instead of the expected dummy_user.
@pytest.mark.usefixtures("other_user", "dummy_user")
def test_returns_the_dummy_user(client: TestClient) -> None:
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json() == {"id": str(DUMMY_USER_ID), "name": DUMMY_USER_NAME}


def test_returns_forbidden_problem_without_the_dummy_user(client: TestClient) -> None:
    response = client.get(PATH)
    problem_body = assert_problem(response, 403)
    assert problem_body == FORBIDDEN_PROBLEM


def test_is_documented_with_its_responses(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"][PATH]["get"]
    success = operation["responses"]["200"]["content"]["application/json"]
    assert success["schema"] == {"$ref": "#/components/schemas/UserResponse"}
    assert operation["responses"]["403"] == {
        "description": "The current user is not authorised",
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/Problem"}
            }
        },
    }
