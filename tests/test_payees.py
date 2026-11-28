"""Tests for the ``/api/v1/payees`` endpoints."""

from datetime import datetime
from uuid import UUID

import httpx2
import pytest
from fastapi.testclient import TestClient
from problems import (
    ARCHIVED_PROBLEM,
    IN_USE_TRANSACTION_PROBLEM,
    NOT_FOUND_PROBLEM,
    assert_problem,
    body_validation_problem,
    parameter_validation_problem,
    without_error_details,
)
from records import World, add_payee, add_transaction, add_transaction_category
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


def put_payee(
    client: TestClient, payee_id: UUID | str, body: dict[str, str]
) -> httpx2.Response:
    return client.put(f"{PATH}/{payee_id}", json=body)


def archive_time(connection: Connection, payee_id: UUID) -> datetime:
    archived_at: datetime = one(
        connection,
        "SELECT archived_at FROM payees WHERE id = :payee_id",
        payee_id=payee_id,
    )
    return archived_at


def payee_id_named(connection: Connection, name: str) -> UUID:
    payee_id: UUID = one(
        connection,
        "SELECT id FROM payees WHERE user_id = :user AND name = :name",
        user=DUMMY_USER_ID,
        name=name,
    )
    return payee_id


def payees_count(connection: Connection, user: UUID = DUMMY_USER_ID) -> int:
    return count(
        connection,
        "SELECT count(*) FROM payees WHERE user_id = :user",
        user=user,
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
    archived_at = archive_time(connection, payee_id)
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
    archived_at = archive_time(connection, payee_id)
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


@pytest.mark.usefixtures("dummy_user")
def test_list_returns_the_users_active_payees_by_name(
    client: TestClient, connection: Connection, alice: World
) -> None:
    add_payee(connection, alice.user, "Corner Store")
    supermarket = add_payee(connection, DUMMY_USER_ID, "Supermarket")
    corner_store = add_payee(connection, DUMMY_USER_ID, "corner store")
    add_payee(connection, DUMMY_USER_ID, "Bakery", archived=True)
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": str(corner_store), "name": "corner store", "archivedAt": None},
            {"id": str(supermarket), "name": "Supermarket", "archivedAt": None},
        ],
        "page": 1,
        "pageSize": 25,
        "totalItems": 2,
        "totalPages": 1,
    }


@pytest.mark.usefixtures("dummy_user")
def test_list_returns_only_archived_payees_when_asked_for(
    client: TestClient, connection: Connection
) -> None:
    add_payee(connection, DUMMY_USER_ID, "Supermarket")
    bakery = add_payee(connection, DUMMY_USER_ID, "Bakery", archived=True)
    archived_at = archive_time(connection, bakery)
    response = client.get(PATH, params={"archived": "true"})
    assert response.status_code == 200
    body = response.json()
    data = [with_parsed_archive_time(payee) for payee in body["data"]]
    assert {**body, "data": data} == {
        "data": [{"id": str(bakery), "name": "Bakery", "archivedAt": archived_at}],
        "page": 1,
        "pageSize": 25,
        "totalItems": 1,
        "totalPages": 1,
    }


@pytest.mark.usefixtures("dummy_user")
def test_list_returns_the_page_of_matching_payees_asked_for(
    client: TestClient, connection: Connection
) -> None:
    add_payee(connection, DUMMY_USER_ID, "Bakery")
    add_payee(connection, DUMMY_USER_ID, "Corner Store")
    add_payee(connection, DUMMY_USER_ID, "Hardware Store")
    farm_store = add_payee(connection, DUMMY_USER_ID, "Farm Store")
    response = client.get(PATH, params={"q": "store", "page": 2, "pageSize": 1})
    assert response.status_code == 200
    assert response.json() == {
        "data": [{"id": str(farm_store), "name": "Farm Store", "archivedAt": None}],
        "page": 2,
        "pageSize": 1,
        "totalItems": 3,
        "totalPages": 3,
    }


@pytest.mark.usefixtures("dummy_user")
def test_list_returns_validation_problem_for_a_sort_other_than_name(
    client: TestClient,
) -> None:
    response = client.get(PATH, params={"sort": "itemCategory"})
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == parameter_validation_problem("sort")


@pytest.mark.usefixtures("dummy_user")
def test_update_returns_the_renamed_payee(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    response = put_payee(client, payee_id, {"name": "Corner Shop"})
    assert response.status_code == 200
    assert response.json() == {
        "id": str(payee_id),
        "name": "Corner Shop",
        "archivedAt": None,
    }


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize("name", ["Corner Store", "CORNER STORE"])
def test_update_accepts_the_payees_own_name_in_any_case(
    client: TestClient, connection: Connection, name: str
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    response = put_payee(client, payee_id, {"name": name})
    assert response.status_code == 200
    assert response.json() == {"id": str(payee_id), "name": name, "archivedAt": None}


@pytest.mark.usefixtures("dummy_user")
def test_update_returns_validation_problem_for_archived_at_in_the_body(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    body = {"name": "Corner Shop", "archivedAt": "2026-11-01T00:00:00Z"}
    response = put_payee(client, payee_id, body)
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem("/archivedAt")


@pytest.mark.usefixtures("dummy_user")
def test_update_returns_name_conflict_problem_for_another_payees_name(
    client: TestClient, connection: Connection
) -> None:
    supermarket_id = add_payee(connection, DUMMY_USER_ID, "Supermarket")
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    response = put_payee(client, payee_id, {"name": "supermarket"})
    problem_body = assert_problem(response, 409)
    assert problem_body == {
        "type": "/problems/name-conflict",
        "title": "Name already in use",
        "status": 409,
        "detail": "A payee named 'Supermarket' already exists.",
        "existing": {
            "id": str(supermarket_id),
            "name": "Supermarket",
            "archivedAt": None,
        },
    }


@pytest.mark.usefixtures("dummy_user")
def test_update_returns_archived_problem_even_if_the_name_is_in_use(
    client: TestClient, connection: Connection
) -> None:
    add_payee(connection, DUMMY_USER_ID, "Supermarket")
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store", archived=True)
    response = put_payee(client, payee_id, {"name": "Supermarket"})
    problem_body = assert_problem(response, 409)
    assert problem_body == ARCHIVED_PROBLEM


@pytest.mark.usefixtures("dummy_user")
def test_update_returns_validation_problem_even_if_the_payee_is_archived(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store", archived=True)
    response = put_payee(client, payee_id, {"name": " "})
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem("/name")


@pytest.mark.usefixtures("dummy_user")
def test_update_returns_not_found_problem_for_another_users_payee(
    client: TestClient, alice: World
) -> None:
    response = put_payee(client, alice.payee, {"name": "Corner Shop"})
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


@pytest.mark.usefixtures("dummy_user")
def test_update_returns_not_found_problem_for_a_malformed_id(
    client: TestClient,
) -> None:
    response = put_payee(client, "not-an-id", {"name": "Corner Shop"})
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


def test_update_documents_its_conflict_problems(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"][f"{PATH}/{{payeeId}}"]
    conflict = operation["put"]["responses"]["409"]
    assert conflict["content"] == {
        "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
    }


@pytest.mark.usefixtures("dummy_user")
def test_archive_returns_the_archived_payee(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    response = client.post(f"{PATH}/{payee_id}/archive")
    assert response.status_code == 200
    assert with_parsed_archive_time(response.json()) == {
        "id": str(payee_id),
        "name": "Corner Store",
        "archivedAt": archive_time(connection, payee_id),
    }


@pytest.mark.usefixtures("dummy_user")
def test_archive_returns_an_archived_payee_unchanged(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store", archived=True)
    archived_at = archive_time(connection, payee_id)
    response = client.post(f"{PATH}/{payee_id}/archive")
    assert response.status_code == 200
    assert with_parsed_archive_time(response.json()) == {
        "id": str(payee_id),
        "name": "Corner Store",
        "archivedAt": archived_at,
    }
    assert archive_time(connection, payee_id) == archived_at


@pytest.mark.usefixtures("dummy_user")
def test_unarchive_returns_the_active_payee(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store", archived=True)
    response = client.post(f"{PATH}/{payee_id}/unarchive")
    assert response.status_code == 200
    assert response.json() == {
        "id": str(payee_id),
        "name": "Corner Store",
        "archivedAt": None,
    }


@pytest.mark.usefixtures("dummy_user")
def test_unarchive_returns_an_active_payee_unchanged(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    response = client.post(f"{PATH}/{payee_id}/unarchive")
    assert response.status_code == 200
    assert response.json() == {
        "id": str(payee_id),
        "name": "Corner Store",
        "archivedAt": None,
    }


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize("action", ["archive", "unarchive"])
def test_archive_actions_return_not_found_problem_for_another_users_payee(
    client: TestClient, alice: World, action: str
) -> None:
    response = client.post(f"{PATH}/{alice.payee}/{action}")
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize("action", ["archive", "unarchive"])
def test_archive_actions_return_not_found_problem_for_a_malformed_id(
    client: TestClient, action: str
) -> None:
    response = client.post(f"{PATH}/not-an-id/{action}")
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


@pytest.mark.usefixtures("dummy_user")
def test_delete_removes_the_payee(client: TestClient, connection: Connection) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    response = client.delete(f"{PATH}/{payee_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert payees_count(connection) == 0


@pytest.mark.usefixtures("dummy_user")
def test_delete_returns_in_use_problem_for_a_payee_a_transaction_uses(
    client: TestClient, connection: Connection
) -> None:
    payee_id = add_payee(connection, DUMMY_USER_ID, "Corner Store")
    category_id = add_transaction_category(connection, DUMMY_USER_ID, "Groceries")
    add_transaction(connection, DUMMY_USER_ID, category_id, payee_id)
    response = client.delete(f"{PATH}/{payee_id}")
    problem_body = assert_problem(response, 409)
    assert problem_body == IN_USE_TRANSACTION_PROBLEM
    assert payees_count(connection) == 1


@pytest.mark.usefixtures("dummy_user")
def test_delete_returns_not_found_problem_for_another_users_payee(
    client: TestClient, connection: Connection, alice: World
) -> None:
    response = client.delete(f"{PATH}/{alice.payee}")
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM
    assert payees_count(connection, alice.user) == 1


@pytest.mark.usefixtures("dummy_user")
def test_delete_returns_not_found_problem_for_a_malformed_id(
    client: TestClient,
) -> None:
    response = client.delete(f"{PATH}/not-an-id")
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


def test_delete_documents_its_in_use_problem(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"][f"{PATH}/{{payeeId}}"]
    conflict = operation["delete"]["responses"]["409"]
    assert conflict["content"] == {
        "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
    }
