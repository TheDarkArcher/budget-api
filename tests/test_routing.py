"""Tests for query parameters sent more than once, in ``app.api.routing``."""

from collections.abc import Callable, Iterator
from typing import Annotated, Any
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from problems import (
    NOT_FOUND_PROBLEM,
    VALIDATION_PROBLEM,
    assert_problem,
    parameter_validation_problem,
    without_error_details,
)
from pydantic import Field

from app.api import v1
from app.api.routing import SingleValueRoute
from app.schemas.pagination import PageParameters

THING_ID = UUID("00000000-0000-7000-8000-00000000000a")
OTHER_ID = UUID("00000000-0000-7000-8000-00000000000b")


class ProbeParameters(PageParameters):
    tag_id: list[UUID] = Field(default_factory=list)


def list_things(
    parameters: Annotated[ProbeParameters, Query()],
    category_id: Annotated[UUID | None, Query(alias="categoryId")] = None,
) -> dict[str, Any]:
    return {"tagIds": parameters.tag_id, "categoryId": category_id}


def get_thing(thing_id: UUID, size: int = 1) -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
def probe_client(
    probe_router: APIRouter, make_app: Callable[[], FastAPI]
) -> Iterator[TestClient]:
    probe_router.add_api_route("/test/things", list_things, methods=["GET"])
    probe_router.add_api_route("/test/things/{thing_id}", get_thing, methods=["GET"])

    with TestClient(make_app()) as client:
        yield client


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    ("query", "parameter"),
    [
        ("page=1&page=2", "page"),
        ("pageSize=5&pageSize=5", "pageSize"),
        (f"categoryId={THING_ID}&categoryId={OTHER_ID}", "categoryId"),
    ],
)
def test_parameter_sent_twice_is_rejected(
    probe_client: TestClient, query: str, parameter: str
) -> None:
    response = probe_client.get(f"/api/v1/test/things?{query}")
    problem_body = assert_problem(response, 422)
    assert problem_body == {
        **VALIDATION_PROBLEM,
        "errors": [
            {"detail": "Send this parameter only once.", "parameter": parameter}
        ],
    }


@pytest.mark.usefixtures("dummy_user")
def test_parameter_sent_twice_is_reported_with_the_other_errors(
    probe_client: TestClient,
) -> None:
    response = probe_client.get(
        "/api/v1/test/things?page=1&page=1&pageSize=0&categoryId=not-an-id"
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == parameter_validation_problem(
        "page", "pageSize", "categoryId"
    )


@pytest.mark.usefixtures("dummy_user")
def test_repeatable_parameter_may_be_sent_twice(probe_client: TestClient) -> None:
    response = probe_client.get(
        f"/api/v1/test/things?tagId={THING_ID}&tagId={OTHER_ID}"
    )
    assert response.status_code == 200
    assert response.json() == {
        "tagIds": [str(THING_ID), str(OTHER_ID)],
        "categoryId": None,
    }


@pytest.mark.usefixtures("dummy_user")
def test_malformed_path_id_returns_not_found_problem_even_if_a_parameter_is_sent_twice(
    probe_client: TestClient,
) -> None:
    response = probe_client.get("/api/v1/test/things/not-an-id?size=1&size=2")
    problem_body = assert_problem(response, 404)
    assert problem_body == NOT_FOUND_PROBLEM


def test_every_v1_route_rejects_parameters_sent_twice() -> None:
    other_routes = [
        context.path
        for context in iter_route_contexts(v1.router.routes)
        if not isinstance(context.original_route, SingleValueRoute)
    ]
    assert other_routes == []
