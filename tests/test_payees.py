"""Tests for the ``/api/v1/payees`` endpoints."""

from uuid import UUID

import httpx2
import pytest
from fastapi.testclient import TestClient
from problems import NOT_FOUND_PROBLEM, assert_problem
from records import World, add_payee
from responses import response_parts, with_parsed_archive_time
from sql import count, one
from sqlalchemy import Connection

from app.core.dummy_user import DUMMY_USER_ID

PATH = "/api/v1/payees"
KEY = "5b0c3f3e-8f0a-4d55-9a6e-2f1d7c3b9e41"


def post_payee(
    client: TestClient, name: str, key: str | None = None
) -> httpx2.Response:
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(PATH, json={"name": name}, headers=headers)


def payee_id_named(connection: Connection, name: str) -> UUID:
    payee_id: UUID = one(
        connection,
        "SELECT id FROM payees WHERE user_id = :user AND name = :name",
        user=DUMMY_USER_ID,
        name=name,
    )
    return payee_id


def payees_count(connection: Connection) -> int:
    return count(
        connection,
        "SELECT count(*) FROM payees WHERE user_id = :user",
        user=DUMMY_USER_ID,
    )


@pytest.mark.usefixtures("dummy_user")
def test_create_returns_the_new_payee_with_its_location(
    client: TestClient, connection: Connection
) -> None:
    response = post_payee(client, "Corner Store")
    payee_id = payee_id_named(connection, "Corner Store")
    assert response.status_code == 201
    assert response.headers["location"] == f"{PATH}/{payee_id}"
    assert response.json() == {
        "id": str(payee_id),
        "name": "Corner Store",
        "archivedAt": None,
    }


@pytest.mark.usefixtures("dummy_user")
def test_create_repeated_with_the_same_idempotency_key_replays_it(
    client: TestClient, connection: Connection
) -> None:
    first = post_payee(client, "Corner Store", KEY)
    repeat = post_payee(client, "Corner Store", KEY)
    assert response_parts(repeat) == response_parts(first)
    assert payees_count(connection) == 1


@pytest.mark.usefixtures("dummy_user")
def test_create_returns_name_conflict_problem_for_a_name_in_use_ignoring_case(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    response = post_payee(client, "CORNER STORE")
    problem_body = assert_problem(response, 409)
    assert problem_body == {
        "type": "/problems/name-conflict",
        "title": "Name already in use",
        "status": 409,
        "detail": "A payee named 'Corner Store' already exists.",
        "existing": {"id": str(payee_id), "name": "Corner Store", "archivedAt": None},
    }
    assert payees_count(connection) == 1


@pytest.mark.usefixtures("dummy_user")
def test_create_returns_name_conflict_problem_for_an_archived_payees_name(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store", archived=True)
    archived_at = one(
        connection,
        "SELECT archived_at FROM payees WHERE id = :payee_id",
        payee_id=payee_id,
    )
    response = post_payee(client, "Corner Store")
    problem_body = assert_problem(response, 409)
    existing = with_parsed_archive_time(problem_body["existing"])
    assert {**problem_body, "existing": existing} == {
        "type": "/problems/name-conflict",
        "title": "Name already in use",
        "status": 409,
        "detail": "A payee named 'Corner Store' already exists.",
        "existing": {
            "id": str(payee_id),
            "name": "Corner Store",
            "archivedAt": archived_at,
        },
    }


@pytest.mark.usefixtures("dummy_user")
def test_create_accepts_a_name_another_user_has(
    client: TestClient, connection: Connection, alice: World
) -> None:
    add_payee(connection, alice.user, "Corner Store")
    response = post_payee(client, "Corner Store")
    payee_id = payee_id_named(connection, "Corner Store")
    assert response.status_code == 201
    assert response.json() == {
        "id": str(payee_id),
        "name": "Corner Store",
        "archivedAt": None,
    }


def test_create_documents_its_name_conflict_problem(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    operation = document["paths"][PATH]["post"]
    schemas = document["components"]["schemas"]
    conflict = operation["responses"]["409"]["content"]["application/problem+json"]
    assert conflict["schema"] == {
        "$ref": "#/components/schemas/PayeeNameConflictProblem"
    }
    properties = schemas["PayeeNameConflictProblem"]["properties"]
    assert properties["type"]["const"] == "/problems/name-conflict"
    assert properties["existing"]["$ref"] == "#/components/schemas/PayeeReference"


@pytest.mark.usefixtures("dummy_user")
def test_get_returns_the_payee(client: TestClient, connection: Connection) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    response = client.get(f"{PATH}/{payee_id}")
    assert response.status_code == 200
    assert response.json() == {
        "id": str(payee_id),
        "name": "Corner Store",
        "archivedAt": None,
    }


@pytest.mark.usefixtures("dummy_user")
def test_get_returns_an_archived_payee_with_its_archive_time(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store", archived=True)
    archived_at = one(
        connection,
        "SELECT archived_at FROM payees WHERE id = :payee_id",
        payee_id=payee_id,
    )
    response = client.get(f"{PATH}/{payee_id}")
    assert response.status_code == 200
    assert with_parsed_archive_time(response.json()) == {
        "id": str(payee_id),
        "name": "Corner Store",
        "archivedAt": archived_at,
    }


@pytest.mark.usefixtures("dummy_user")
def test_get_returns_not_found_problem_for_another_users_payee(
    client: TestClient, alice: World
) -> None:
    response = client.get(f"{PATH}/{alice.payee}")
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


@pytest.mark.usefixtures("dummy_user")
def test_get_returns_not_found_problem_for_a_malformed_id(
    client: TestClient,
) -> None:
    response = client.get(f"{PATH}/not-an-id")
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM
