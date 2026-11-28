"""Tests for the problem+json error responses of ``/api/v1``."""

import logging
from collections.abc import Callable, Iterator
from datetime import datetime
from functools import partial
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi import APIRouter, FastAPI, Query, Response
from fastapi.testclient import TestClient
from problems import (
    ARCHIVED_PROBLEM,
    FORBIDDEN_PROBLEM,
    IN_USE_TRANSACTION_PROBLEM,
    INTERNAL_ERROR_PROBLEM,
    NOT_FOUND_PROBLEM,
    assert_exception_logged,
    assert_problem,
    body_validation_problem,
    parameter_validation_problem,
    without_error_details,
)

from app.api.dependencies import IdempotentCreateDep
from app.api.idempotency import NewRecord
from app.api.problems import (
    INVALID_REFERENCE,
    NAME_CONFLICT,
    ProblemError,
)
from app.core.errors import (
    ArchivedError,
    Blocker,
    DomainError,
    InUseError,
    TypeChangeError,
)
from app.schemas.base import ApiModel
from app.schemas.problems import ProblemErrorEntry

INTERNAL_DETAIL = "connection string postgresql://secret"
EXISTING_ID = UUID("00000000-0000-7000-8000-00000000000a")
THING_ID = UUID("00000000-0000-7000-8000-00000000000b")
# Each domain error the API reports, keyed by the probe route's ``kind``.
DOMAIN_ERRORS: dict[str, Callable[[], DomainError]] = {
    "in-use-transaction": partial(InUseError, Blocker.TRANSACTION),
    "in-use-item": partial(InUseError, Blocker.ITEM),
    "in-use-item-category": partial(InUseError, Blocker.ITEM_CATEGORY),
    "archived": ArchivedError,
    "type-change": TypeChangeError,
}
# What a create can raise once it runs, in the error order.
CREATE_ERRORS = ("invalid-reference", "name-conflict")


class ProbeSize(ApiModel):
    unit_name: str


class ProbeBody(ApiModel):
    page_size: int
    sizes: list[ProbeSize]


class ProbeThing(ApiModel):
    thing_id: UUID


class ProbeReference(ApiModel):
    id: UUID
    name: str
    archived_at: datetime | None


def read_only() -> dict[str, bool]:
    return {"ok": True}


def accept_body(body: ProbeBody) -> dict[str, bool]:
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


def raise_domain_error(kind: str) -> None:
    raise DOMAIN_ERRORS[kind]()


def refuse_create(kind: str) -> None:
    match kind:
        case "invalid-reference":
            invalid_reference()
        case "name-conflict":
            conflict()


def create_thing(
    body: ProbeBody,
    creation: IdempotentCreateDep,
    page_size: Annotated[int, Query(alias="pageSize")] = 1,
    refuse: Annotated[str | None, Query()] = None,
) -> Response:
    def create() -> NewRecord:
        if refuse is not None:
            refuse_create(refuse)
        thing = ProbeThing(thing_id=uuid4())
        return NewRecord(thing, f"/api/v1/test/things/{thing.thing_id}")

    return creation.run(body, create)


def replace_thing(thing_id: UUID, body: ProbeBody) -> dict[str, bool]:
    return {"ok": True}


def post_thing(
    client: TestClient,
    key: str,
    *,
    name: str = "g",
    refuse: str | None = None,
) -> httpx2.Response:
    return client.post(
        "/api/v1/test/things",
        params={} if refuse is None else {"refuse": refuse},
        json={"pageSize": 1, "sizes": [{"unitName": name}]},
        headers={"Idempotency-Key": key},
    )


@pytest.fixture
def probe_client(
    probe_router: APIRouter, make_app: Callable[[], FastAPI]
) -> Iterator[TestClient]:
    probe_router.add_api_route("/test/read-only", read_only, methods=["GET"])
    probe_router.add_api_route("/test/body", accept_body, methods=["POST"])
    probe_router.add_api_route("/test/fail", fail, methods=["GET"])
    probe_router.add_api_route("/test/conflict", conflict, methods=["POST"])
    probe_router.add_api_route(
        "/test/invalid-reference", invalid_reference, methods=["POST"]
    )
    probe_router.add_api_route("/test/things", create_thing, methods=["POST"])
    probe_router.add_api_route(
        "/test/things/{thing_id}", replace_thing, methods=["PUT"]
    )
    probe_router.add_api_route(
        "/test/domain-error", raise_domain_error, methods=["POST"]
    )

    with TestClient(make_app()) as client:
        yield client


@pytest.mark.usefixtures("dummy_user")
def test_unknown_path_returns_not_found_problem(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/test/unknown")
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


@pytest.mark.usefixtures("dummy_user")
def test_unsupported_method_returns_method_not_allowed_problem_with_allow(
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
def test_invalid_body_returns_validation_problem_with_pointers(
    probe_client: TestClient,
) -> None:
    response = probe_client.post(
        "/api/v1/test/body",
        json={"pageSize": "many", "sizes": [{"unitName": "g"}, {"unitName": 1}]},
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem(
        "/pageSize", "/sizes/1/unitName"
    )


@pytest.mark.usefixtures("dummy_user")
def test_malformed_json_body_returns_validation_problem_for_the_whole_body(
    probe_client: TestClient,
) -> None:
    response = probe_client.post(
        "/api/v1/test/body",
        content=b'{"pageSize": ',
        headers={"Content-Type": "application/json"},
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem("")


@pytest.mark.usefixtures("dummy_user")
def test_invalid_parameters_are_named_in_the_validation_problem(
    probe_client: TestClient,
) -> None:
    response = probe_client.post(
        "/api/v1/test/things",
        params={"pageSize": "many"},
        json={"pageSize": 1, "sizes": []},
        headers={"Idempotency-Key": "k" * 256},
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == parameter_validation_problem(
        "Idempotency-Key", "pageSize"
    )


@pytest.mark.usefixtures("dummy_user")
def test_unexpected_error_returns_internal_error_problem_without_internals(
    probe_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        response = probe_client.get("/api/v1/test/fail")
    problem_body = assert_problem(response, 500)
    assert problem_body == INTERNAL_ERROR_PROBLEM
    assert "secret" not in response.text
    assert "Traceback" not in response.text
    assert_exception_logged(caplog, INTERNAL_DETAIL)


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
def test_malformed_path_id_returns_not_found_problem(probe_client: TestClient) -> None:
    response = probe_client.put(
        "/api/v1/test/things/not-an-id",
        json={"pageSize": 1, "sizes": []},
    )
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


@pytest.mark.usefixtures("dummy_user")
def test_malformed_path_id_returns_not_found_problem_even_if_the_body_is_invalid(
    probe_client: TestClient,
) -> None:
    response = probe_client.put("/api/v1/test/things/not-an-id", json={})
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


@pytest.mark.usefixtures("dummy_user")
def test_well_formed_path_id_returns_validation_problem_for_the_body(
    probe_client: TestClient,
) -> None:
    response = probe_client.put(f"/api/v1/test/things/{THING_ID}", json={})
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem(
        "/pageSize", "/sizes"
    )


@pytest.mark.parametrize(
    ("method", "path", "request_options"),
    [
        pytest.param(
            "POST", "/api/v1/test/body", {"json": {"pageSize": "many"}}, id="body"
        ),
        pytest.param(
            "POST",
            "/api/v1/test/body",
            {
                "content": b'{"pageSize": ',
                "headers": {"Content-Type": "application/json"},
            },
            id="malformed-json",
        ),
        pytest.param(
            "POST",
            "/api/v1/test/things",
            {"params": {"pageSize": "many"}, "headers": {"Idempotency-Key": "k" * 256}},
            id="parameters",
        ),
        pytest.param(
            "PUT", "/api/v1/test/things/not-an-id", {"json": {}}, id="path-id"
        ),
    ],
)
def test_missing_current_user_returns_forbidden_problem_even_if_the_request_is_invalid(
    probe_client: TestClient,
    method: str,
    path: str,
    request_options: dict[str, Any],
) -> None:
    response = probe_client.request(method, path, **request_options)
    problem_body = assert_problem(response, 403)
    assert problem_body == FORBIDDEN_PROBLEM


@pytest.mark.usefixtures("dummy_user")
def test_invalid_request_returns_validation_problem_even_if_its_key_was_used(
    probe_client: TestClient,
) -> None:
    assert post_thing(probe_client, "key").status_code == 201
    response = probe_client.post(
        "/api/v1/test/things", json={}, headers={"Idempotency-Key": "key"}
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem(
        "/pageSize", "/sizes"
    )


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize("refuse", CREATE_ERRORS)
def test_stored_response_is_replayed_even_if_the_create_would_be_refused(
    probe_client: TestClient, refuse: str
) -> None:
    original = post_thing(probe_client, "key")
    assert post_thing(probe_client, "other", refuse=refuse).is_client_error
    repeat = post_thing(probe_client, "key", refuse=refuse)
    assert repeat.status_code == original.status_code == 201
    assert repeat.content == original.content
    assert repeat.headers == original.headers


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize("refuse", CREATE_ERRORS)
def test_reused_key_returns_mismatch_problem_even_if_the_create_would_be_refused(
    probe_client: TestClient, refuse: str
) -> None:
    assert post_thing(probe_client, "key").status_code == 201
    response = post_thing(probe_client, "key", name="kg", refuse=refuse)
    problem_body = assert_problem(response, 422)
    assert problem_body == {
        "type": "/problems/idempotency-key-mismatch",
        "title": "Idempotency key reused",
        "status": 422,
        "detail": "The Idempotency-Key was already used with a different request.",
    }


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        pytest.param(
            "in-use-transaction",
            IN_USE_TRANSACTION_PROBLEM,
            id="in use by a transaction",
        ),
        pytest.param(
            "in-use-item",
            {
                "type": "/problems/in-use/item",
                "title": "In use by an item",
                "status": 409,
                "detail": "An item uses the record, so it can't be deleted;"
                " archive it instead.",
            },
            id="in use by an item",
        ),
        pytest.param(
            "in-use-item-category",
            {
                "type": "/problems/in-use/item-category",
                "title": "Linked to an active item category",
                "status": 409,
                "detail": "The record is linked to an active item category, so it"
                " can't be deleted.",
            },
            id="linked to an active item category",
        ),
        pytest.param(
            "archived",
            ARCHIVED_PROBLEM,
            id="archived",
        ),
        pytest.param(
            "type-change",
            {
                "type": "/problems/validation",
                "title": "Validation failed",
                "status": 422,
                "detail": "The request isn't valid; see errors for each problem.",
                "errors": [
                    {
                        "detail": "A transaction category's type can't be changed.",
                        "pointer": "/type",
                    }
                ],
            },
            id="type change",
        ),
    ],
)
def test_domain_error_returns_its_problem(
    probe_client: TestClient, kind: str, expected: dict[str, Any]
) -> None:
    response = probe_client.post("/api/v1/test/domain-error", params={"kind": kind})
    problem_body = assert_problem(response, expected["status"])
    assert problem_body == expected
