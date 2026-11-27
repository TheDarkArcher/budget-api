"""Tests for request bodies refusing fields they don't declare."""

from collections.abc import Callable, Iterator
from typing import Annotated

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.testclient import TestClient
from problems import assert_problem, body_validation_problem, without_error_details
from pydantic import Field

from app.schemas.base import ApiModel, RequestBody


class ProbeSize(RequestBody):
    value: str


class ProbeBody(RequestBody):
    name: str
    sizes: list[ProbeSize] = Field(default_factory=list)


class ProbeParameters(ApiModel):
    q: str = ""


def echo_body(body: ProbeBody) -> ProbeBody:
    return body


def echo_parameters(
    parameters: Annotated[ProbeParameters, Query()],
) -> ProbeParameters:
    return parameters


@pytest.fixture
def probe_client(
    probe_router: APIRouter, make_app: Callable[[], FastAPI]
) -> Iterator[TestClient]:
    probe_router.add_api_route("/test/bodies", echo_body, methods=["POST"])
    probe_router.add_api_route("/test/parameters", echo_parameters, methods=["GET"])

    with TestClient(make_app()) as client:
        yield client


@pytest.mark.usefixtures("dummy_user")
def test_body_with_only_declared_fields_is_accepted(probe_client: TestClient) -> None:
    body = {"name": "Milk", "sizes": [{"value": "2"}]}
    response = probe_client.post("/api/v1/test/bodies", json=body)
    assert response.status_code == 200
    assert response.json() == body


@pytest.mark.usefixtures("dummy_user")
def test_undeclared_field_returns_body_validation_problem(
    probe_client: TestClient,
) -> None:
    body = {"name": "Milk", "archivedAt": None}
    response = probe_client.post("/api/v1/test/bodies", json=body)
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem("/archivedAt")


@pytest.mark.usefixtures("dummy_user")
def test_undeclared_field_in_a_nested_object_returns_body_validation_problem(
    probe_client: TestClient,
) -> None:
    body = {"name": "Milk", "sizes": [{"value": "2"}, {"value": "1", "id": "x"}]}
    response = probe_client.post("/api/v1/test/bodies", json=body)
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem("/sizes/1/id")


@pytest.mark.usefixtures("dummy_user")
def test_each_undeclared_field_has_its_own_errors_entry(
    probe_client: TestClient,
) -> None:
    body = {"name": "Milk", "id": "x", "archivedAt": None}
    response = probe_client.post("/api/v1/test/bodies", json=body)
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem(
        "/id", "/archivedAt"
    )


@pytest.mark.usefixtures("dummy_user")
def test_undeclared_query_parameter_is_ignored(probe_client: TestClient) -> None:
    response = probe_client.get(
        "/api/v1/test/parameters", params={"q": "milk", "serach": "milk"}
    )
    assert response.status_code == 200
    assert response.json() == {"q": "milk"}
