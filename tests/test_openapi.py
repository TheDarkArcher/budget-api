"""Tests for how ``app.api.openapi`` documents the API's error responses."""

from collections.abc import Callable, Iterator
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.openapi import documented_problem
from app.schemas.base import ApiModel


class ProbeBody(ApiModel):
    page_size: int


def accept_body(body: ProbeBody) -> dict[str, bool]:
    return {"ok": True}


def get_thing(thing_id: UUID) -> dict[str, bool]:
    return {"ok": True}


def replace_thing(thing_id: UUID, body: ProbeBody) -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
def probe_client(
    probe_router: APIRouter, make_app: Callable[[], FastAPI]
) -> Iterator[TestClient]:
    probe_router.add_api_route("/test/body", accept_body, methods=["POST"])
    probe_router.add_api_route("/test/things/{thing_id}", get_thing, methods=["GET"])
    probe_router.add_api_route(
        "/test/things/{thing_id}", replace_thing, methods=["PUT"]
    )
    probe_router.add_api_route(
        "/test/documented-conflict",
        accept_body,
        methods=["POST"],
        responses={409: documented_problem("The name is already in use")},
    )

    with TestClient(make_app()) as client:
        yield client


def test_declared_problem_response_is_documented_as_problem_json(
    probe_client: TestClient,
) -> None:
    paths = probe_client.get("/openapi.json").json()["paths"]
    responses = paths["/api/v1/test/documented-conflict"]["post"]["responses"]
    assert responses["409"] == {
        "description": "The name is already in use",
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/Problem"}
            }
        },
    }


def test_only_operations_that_can_fail_validation_document_it(
    probe_client: TestClient,
) -> None:
    # A malformed path id returns 404, so an operation whose only input is
    # its path can't return 422.
    thing = probe_client.get("/openapi.json").json()["paths"][
        "/api/v1/test/things/{thing_id}"
    ]
    assert "422" not in thing["get"]["responses"]
    assert "422" in thing["put"]["responses"]


def test_validation_failure_is_documented_as_a_problem(
    probe_client: TestClient,
) -> None:
    document = probe_client.get("/openapi.json").json()
    responses = document["paths"]["/api/v1/test/body"]["post"]["responses"]
    assert responses["422"] == {
        "description": "Validation Error",
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/Problem"}
            }
        },
    }
    assert "HTTPValidationError" not in document["components"]["schemas"]
    assert "ValidationError" not in document["components"]["schemas"]


def test_problem_schema_documents_members_as_sent(probe_client: TestClient) -> None:
    # Unset members are left out of a problem rather than sent as null, and
    # `type` is always sent.
    schemas = probe_client.get("/openapi.json").json()["components"]["schemas"]
    problem, entry = schemas["Problem"], schemas["ProblemErrorEntry"]
    assert problem["required"] == ["type", "title", "status", "detail"]
    assert "default" not in problem["properties"]["type"]
    assert problem["properties"]["errors"]["type"] == "array"
    assert entry["required"] == ["detail"]
    assert entry["properties"]["pointer"]["type"] == "string"
    assert entry["properties"]["parameter"]["type"] == "string"
