"""Tests for the paged list response in ``app.schemas.pagination``."""

from collections.abc import Callable, Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.schemas.base import ApiModel
from app.schemas.pagination import Page


class ProbeRecord(ApiModel):
    record_name: str


def list_records() -> Page[ProbeRecord]:
    return Page[ProbeRecord](
        data=[ProbeRecord(record_name="Bread"), ProbeRecord(record_name="Milk")],
        page=2,
        page_size=2,
        total_items=5,
        total_pages=3,
    )


@pytest.fixture
def probe_client(
    probe_router: APIRouter, make_app: Callable[[], FastAPI]
) -> Iterator[TestClient]:
    probe_router.add_api_route("/test/records", list_records, methods=["GET"])

    with TestClient(make_app()) as client:
        yield client


@pytest.mark.usefixtures("dummy_user")
def test_paged_response_holds_the_page_and_its_totals(
    probe_client: TestClient,
) -> None:
    response = probe_client.get("/api/v1/test/records")
    assert response.status_code == 200
    assert response.json() == {
        "data": [{"recordName": "Bread"}, {"recordName": "Milk"}],
        "page": 2,
        "pageSize": 2,
        "totalItems": 5,
        "totalPages": 3,
    }
