"""Tests for the OpenAPI schema's version and the export script."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from export_openapi import OPENAPI_PATH, export, openapi_json
from fastapi.testclient import TestClient

from app import __version__
from app.core.config import get_settings
from app.main import create_app

BUILD_LABEL = "0.2.0-dev.47+1a2b3c4"


def served_version() -> str:
    with TestClient(create_app()) as client:
        version: str = client.get("/openapi.json").json()["info"]["version"]
    return version


@pytest.fixture(autouse=True)
def unreachable_database() -> Iterator[None]:
    # Nothing listens on port 1, so any attempt to connect would fail.
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", "postgresql://user:password@127.0.0.1:1/budget")
        mp.delenv("APP_BUILD", raising=False)
        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture
def build_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_BUILD", BUILD_LABEL)
    get_settings.cache_clear()


def test_the_committed_openapi_json_matches_the_app() -> None:
    assert OPENAPI_PATH.read_text(encoding="utf-8") == openapi_json(), (
        "openapi.json is out of date; run `uv run poe export-openapi`"
    )


def test_writes_the_apps_schema(tmp_path: Path) -> None:
    path = tmp_path / "openapi.json"
    export(path)
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == create_app().openapi()
    assert text.endswith("}\n")


def test_exports_the_same_text_every_time() -> None:
    assert openapi_json() == openapi_json()


@pytest.mark.usefixtures("build_label")
def test_exports_the_plain_version_even_with_a_build_label() -> None:
    assert json.loads(openapi_json())["info"]["version"] == __version__


@pytest.mark.usefixtures("build_label")
def test_the_served_schema_reports_the_build_label() -> None:
    assert served_version() == BUILD_LABEL


def test_the_served_schema_reports_the_plain_version_without_a_build_label() -> None:
    assert served_version() == __version__
