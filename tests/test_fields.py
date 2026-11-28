"""Tests for the shared field types and reference base in ``app.schemas.fields``."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from problems import assert_problem, body_validation_problem, without_error_details

from app.schemas.base import ApiModel
from app.schemas.fields import DecimalString, Name, Reference

ACTIVE_ID = UUID("00000000-0000-7000-8000-00000000000a")
ARCHIVED_ID = UUID("00000000-0000-7000-8000-00000000000b")
ARCHIVED_AT = datetime(2026, 11, 24, 9, 30, tzinfo=UTC)
VALID_BODY = {"name": "Corner Store", "value": "500"}


class ProbeFields(ApiModel):
    name: Name
    value: DecimalString


class ProbeReference(Reference):
    pass


def echo_fields(body: ProbeFields) -> ProbeFields:
    return body


def get_stored_fields() -> ProbeFields:
    return ProbeFields(name="Corner Store", value=Decimal("500.00"))


def list_references() -> list[ProbeReference]:
    return [
        ProbeReference(id=ACTIVE_ID, name="Corner Store", archived_at=None),
        ProbeReference(id=ARCHIVED_ID, name="Old Market", archived_at=ARCHIVED_AT),
    ]


@pytest.fixture
def probe_client(
    probe_router: APIRouter, make_app: Callable[[], FastAPI]
) -> Iterator[TestClient]:
    probe_router.add_api_route("/test/fields", echo_fields, methods=["POST"])
    probe_router.add_api_route("/test/fields", get_stored_fields, methods=["GET"])
    probe_router.add_api_route("/test/references", list_references, methods=["GET"])

    with TestClient(make_app()) as client:
        yield client


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    ("sent", "kept"),
    [
        ("  Corner Store \t", "Corner Store"),
        ("x", "x"),
        (f" {'x' * 100} ", "x" * 100),
    ],
)
def test_name_is_trimmed_and_kept(
    probe_client: TestClient, sent: str, kept: str
) -> None:
    response = probe_client.post(
        "/api/v1/test/fields", json={**VALID_BODY, "name": sent}
    )
    assert response.status_code == 200
    assert response.json() == {**VALID_BODY, "name": kept}


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize("sent", ["", "   ", "x" * 101])
def test_name_outside_its_length_after_trimming_is_rejected(
    probe_client: TestClient, sent: str
) -> None:
    response = probe_client.post(
        "/api/v1/test/fields", json={**VALID_BODY, "name": sent}
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem("/name")


@pytest.mark.usefixtures("dummy_user")
def test_name_with_a_nul_character_is_rejected(
    probe_client: TestClient,
) -> None:
    response = probe_client.post(
        "/api/v1/test/fields", json={**VALID_BODY, "name": "Corner\x00Store"}
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem("/name")


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    ("sent", "returned"),
    [
        ("500", "500"),
        ("500.0", "500"),
        ("1.350", "1.35"),
        ("3.5", "3.5"),
        ("0", "0"),
        ("0.00", "0"),
        ("007", "7"),
        ("1000", "1000"),
        (" \t12.50 ", "12.5"),
    ],
)
def test_decimal_string_is_trimmed_and_returned_without_trailing_zeros(
    probe_client: TestClient, sent: str, returned: str
) -> None:
    response = probe_client.post(
        "/api/v1/test/fields", json={**VALID_BODY, "value": sent}
    )
    assert response.status_code == 200
    assert response.json() == {**VALID_BODY, "value": returned}


@pytest.mark.usefixtures("dummy_user")
def test_stored_decimal_is_returned_as_a_string_without_trailing_zeros(
    probe_client: TestClient,
) -> None:
    response = probe_client.get("/api/v1/test/fields")
    assert response.status_code == 200
    assert response.json() == {**VALID_BODY, "value": "500"}


@pytest.mark.usefixtures("dummy_user")
@pytest.mark.parametrize(
    "sent",
    [
        500,
        3.5,
        None,
        "",
        " ",
        "1.",
        ".5",
        "-1",
        "+1",
        "1e3",
        "1,5",
        "1 000",
        "NaN",
        "Infinity",
        "٣",
    ],
)
def test_decimal_that_is_not_a_plain_decimal_string_is_rejected(
    probe_client: TestClient, sent: Any
) -> None:
    response = probe_client.post(
        "/api/v1/test/fields", json={**VALID_BODY, "value": sent}
    )
    problem_body = assert_problem(response, 422)
    assert without_error_details(problem_body) == body_validation_problem("/value")


@pytest.mark.usefixtures("dummy_user")
def test_reference_carries_id_name_and_archive_time(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/test/references")
    assert response.status_code == 200
    assert response.json() == [
        {"id": str(ACTIVE_ID), "name": "Corner Store", "archivedAt": None},
        {
            "id": str(ARCHIVED_ID),
            "name": "Old Market",
            "archivedAt": "2026-11-24T09:30:00Z",
        },
    ]
