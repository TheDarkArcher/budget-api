"""Tests for the CORS configuration."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from app.core.config import get_settings
from app.main import create_app

ALLOWED = "http://frontend.test"
SECOND = "http://second.test"
OTHER = "http://elsewhere.test"


def preflight(
    client: TestClient,
    origin: str,
    method: str = "GET",
    request_headers: str | None = None,
) -> Response:
    headers = {"Origin": origin, "Access-Control-Request-Method": method}
    if request_headers is not None:
        headers["Access-Control-Request-Headers"] = request_headers
    return client.options("/health/live", headers=headers)


@pytest.fixture
def cors_client() -> Iterator[TestClient]:
    with pytest.MonkeyPatch.context() as mp:
        # Settings require a database URL, but these requests never connect.
        mp.setenv("DATABASE_URL", "postgresql://user:password@db.test/budget")
        mp.setenv("CORS_ALLOWED_ORIGINS", f"{ALLOWED}, {SECOND}")
        get_settings.cache_clear()
        with TestClient(create_app()) as client:
            yield client
    get_settings.cache_clear()


def test_preflight_from_allowed_origin(cors_client: TestClient) -> None:
    response = preflight(cors_client, ALLOWED)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_from_other_origin_is_refused(cors_client: TestClient) -> None:
    response = preflight(cors_client, OTHER)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_preflight_for_method_in_the_api_is_allowed(
    cors_client: TestClient, method: str
) -> None:
    assert preflight(cors_client, ALLOWED, method=method).status_code == 200


def test_preflight_for_method_not_in_the_api_is_refused(
    cors_client: TestClient,
) -> None:
    assert preflight(cors_client, ALLOWED, method="TRACE").status_code == 400


def test_preflight_for_content_type_header_is_allowed(
    cors_client: TestClient,
) -> None:
    response = preflight(cors_client, ALLOWED, request_headers="Content-Type")
    assert response.status_code == 200


def test_preflight_for_unlisted_header_is_refused(cors_client: TestClient) -> None:
    response = preflight(cors_client, ALLOWED, request_headers="Authorization")
    assert response.status_code == 400


@pytest.mark.parametrize("origin", [ALLOWED, SECOND])
def test_every_listed_origin_is_allowed_after_trimming(
    cors_client: TestClient, origin: str
) -> None:
    response = preflight(cors_client, origin)
    assert response.headers["access-control-allow-origin"] == origin


def test_response_exposes_location_to_allowed_origin(cors_client: TestClient) -> None:
    response = cors_client.get("/health/live", headers={"Origin": ALLOWED})
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert response.headers["access-control-expose-headers"] == "Location"


def test_response_to_other_origin_has_no_cors_headers(
    cors_client: TestClient,
) -> None:
    response = cors_client.get("/health/live", headers={"Origin": OTHER})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
