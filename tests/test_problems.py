"""Tests for the problem+json error responses of ``/api/v1``."""

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Header, Query
from fastapi.testclient import TestClient
from problems import assert_problem, without_error_details
from sqlalchemy import Connection

from app.api import v1
from app.api.problems import INVALID_REFERENCE, NAME_CONFLICT, ProblemError
from app.database.engine import get_connection
from app.main import create_app
from app.schemas.base import ApiModel
from app.schemas.problems import ProblemErrorEntry

INTERNAL_DETAIL = "connection string postgresql://secret"
EXISTING_ID = UUID("00000000-0000-7000-8000-00000000000a")
THING_ID = UUID("00000000-0000-7000-8000-00000000000b")


class ProbeSize(ApiModel):
    unit_name: str


class ProbeBody(ApiModel):
    page_size: int
    sizes: list[ProbeSize]


class ProbeReference(ApiModel):
    id: UUID
    name: str
    archived_at: datetime | None


def read_only() -> dict[str, bool]:
    return {"ok": True}


def accept_body(body: ProbeBody) -> dict[str, bool]:
    return {"ok": True}


def accept_parameters(
    page_size: Annotated[int, Query(alias="pageSize")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", max_length=3)],
) -> dict[str, bool]:
    return {"ok": True}


def fail() -> None:
    raise RuntimeError(INTERNAL_DETAIL)


def conflict() -> None:
    existing = ProbeReference(id=EXISTING_ID, name="Corner Store", archived_at=None)
    raise ProblemError(
        NAME_CONFLICT, "A payee named 'Corner Store' exists.", existing=existing
    )


def invalid_reference() -> None:
    error = ProblemErrorEntry(
        detail="No such item category.", pointer="/itemCategoryId"
    )
    raise ProblemError(
        INVALID_REFERENCE,
        "The request refers to records that can't be used.",
        errors=[error],
    )


def replace_thing(thing_id: UUID, body: ProbeBody) -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
def probe_client(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    # Probe routes on the real v1 router, added to a copy of its routes that
    # monkeypatch swaps back after the test.
    monkeypatch.setattr(v1.router, "routes", list(v1.router.routes))
    v1.router.add_api_route("/test/read-only", read_only, methods=["GET"])
    v1.router.add_api_route("/test/body", accept_body, methods=["POST"])
    v1.router.add_api_route("/test/parameters", accept_parameters, methods=["GET"])
    v1.router.add_api_route("/test/fail", fail, methods=["GET"])
    v1.router.add_api_route("/test/conflict", conflict, methods=["POST"])
    v1.router.add_api_route(
        "/test/invalid-reference", invalid_reference, methods=["POST"]
    )
    v1.router.add_api_route("/test/things/{thing_id}", replace_thing, methods=["PUT"])
    app = create_app()

    # A savepoint per request, as in conftest.py's app fixture.
    def override() -> Iterator[Connection]:
        with connection.begin_nested():
            yield connection

    app.dependency_overrides[get_connection] = override
    with TestClient(app) as client:
        yield client


@pytest.mark.usefixtures("dummy_user")
def test_unknown_path_is_a_not_found_problem(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/test/unknown")
    problem_body = assert_problem(response, 404)
    assert problem_body == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
    }


@pytest.mark.usefixtures("dummy_user")
def test_unsupported_method_is_a_problem_that_keeps_allow(
    probe_client: TestClient,
) -> None:
    response = probe_client.delete("/api/v1/test/read-only")
    problem_body = assert_problem(response, 405)
    assert response.headers["allow"] == "GET"
    assert problem_body == {
        "type": "about:blank",
        "title": "Method Not Allowed",
        "status": 405,
        "detail": "Method Not Allowed",
    }


@pytest.mark.usefixtures("dummy_user")
def test_invalid_body_is_a_validation_problem_with_pointers(
    probe_client: TestClient,
) -> None:
    response = probe_client.post(
        "/api/v1/test/body",
        json={"pageSize": "many", "sizes": [{"unitName": "g"}, {"unitName": 1}]},
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == {
        "type": "/problems/validation",
        "title": "Validation failed",
        "status": 422,
        "detail": "The request isn't valid; see errors for each problem.",
        "errors": [{"pointer": "/pageSize"}, {"pointer": "/sizes/1/unitName"}],
    }


@pytest.mark.usefixtures("dummy_user")
def test_malformed_json_body_points_at_the_whole_body(
    probe_client: TestClient,
) -> None:
    response = probe_client.post(
        "/api/v1/test/body",
        content=b'{"pageSize": ',
        headers={"Content-Type": "application/json"},
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == {
        "type": "/problems/validation",
        "title": "Validation failed",
        "status": 422,
        "detail": "The request isn't valid; see errors for each problem.",
        "errors": [{"pointer": ""}],
    }


@pytest.mark.usefixtures("dummy_user")
def test_invalid_parameters_are_named_in_the_validation_problem(
    probe_client: TestClient,
) -> None:
    response = probe_client.get(
        "/api/v1/test/parameters",
        params={"pageSize": "many"},
        headers={"Idempotency-Key": "too long"},
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == {
        "type": "/problems/validation",
        "title": "Validation failed",
        "status": 422,
        "detail": "The request isn't valid; see errors for each problem.",
        "errors": [{"parameter": "pageSize"}, {"parameter": "Idempotency-Key"}],
    }


@pytest.mark.usefixtures("dummy_user")
def test_unexpected_error_is_a_logged_problem_without_internals(
    probe_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        response = probe_client.get("/api/v1/test/fail")
    problem_body = assert_problem(response, 500)
    assert problem_body == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "An unexpected error occurred.",
    }
    assert "secret" not in response.text
    assert "Traceback" not in response.text
    assert any(
        record.exc_info is not None and INTERNAL_DETAIL in str(record.exc_info[1])
        for record in caplog.records
    )


@pytest.mark.usefixtures("dummy_user")
def test_named_problem_has_its_type_title_and_extension_members(
    probe_client: TestClient,
) -> None:
    response = probe_client.post("/api/v1/test/conflict")
    problem_body = assert_problem(response, 409)
    assert problem_body == {
        "type": "/problems/name-conflict",
        "title": "Name already in use",
        "status": 409,
        "detail": "A payee named 'Corner Store' exists.",
        "existing": {
            "id": str(EXISTING_ID),
            "name": "Corner Store",
            "archivedAt": None,
        },
    }


@pytest.mark.usefixtures("dummy_user")
def test_named_problem_carries_its_errors_entries(probe_client: TestClient) -> None:
    response = probe_client.post("/api/v1/test/invalid-reference")
    problem_body = assert_problem(response, 422)
    assert problem_body == {
        "type": "/problems/invalid-reference",
        "title": "Invalid reference",
        "status": 422,
        "detail": "The request refers to records that can't be used.",
        "errors": [{"detail": "No such item category.", "pointer": "/itemCategoryId"}],
    }


@pytest.mark.usefixtures("dummy_user")
def test_malformed_path_id_is_not_found(probe_client: TestClient) -> None:
    response = probe_client.put(
        "/api/v1/test/things/not-an-id",
        json={"pageSize": 1, "sizes": []},
    )
    problem_body = assert_problem(response, 404)
    assert problem_body == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
    }


@pytest.mark.usefixtures("dummy_user")
def test_malformed_path_id_is_not_found_ahead_of_an_invalid_body(
    probe_client: TestClient,
) -> None:
    response = probe_client.put("/api/v1/test/things/not-an-id", json={})
    problem_body = assert_problem(response, 404)
    assert problem_body == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
    }


@pytest.mark.usefixtures("dummy_user")
def test_well_formed_path_id_still_gets_body_validation(
    probe_client: TestClient,
) -> None:
    response = probe_client.put(f"/api/v1/test/things/{THING_ID}", json={})
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == {
        "type": "/problems/validation",
        "title": "Validation failed",
        "status": 422,
        "detail": "The request isn't valid; see errors for each problem.",
        "errors": [{"pointer": "/pageSize"}, {"pointer": "/sizes"}],
    }
