"""Shared fixtures: a Postgres 18 container, migrations and a test client."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings, get_settings
from app.database.engine import get_connection, get_engine, get_ping_engine
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def clear_caches() -> None:
    """Forget cached settings and engines so they're rebuilt from the env."""
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_ping_engine.cache_clear()


def make_alembic_config(connection: Connection) -> Config:
    """Alembic config that migrates the given connection."""
    config = Config(ROOT / "alembic.ini", toml_file=ROOT / "pyproject.toml")
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="session", autouse=True)
def ignore_env_file() -> Iterator[None]:
    # Settings come only from the environment the tests set up.
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(Settings.model_config, "env_file", None)
        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:18", driver=None) as container:
        yield container


@pytest.fixture(scope="session")
def engine(postgres: PostgresContainer) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", postgres.get_connection_url())
        clear_caches()
        engine = get_engine()
        with engine.begin() as connection:
            command.upgrade(make_alembic_config(connection), "head")
        yield engine
        engine.dispose()
    clear_caches()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def alembic_config() -> Callable[[Connection], Config]:
    return make_alembic_config


@pytest.fixture
def app(connection: Connection) -> FastAPI:
    # A savepoint per request, so a failed request rolls back its writes
    # as get_connection's transaction does.
    def override() -> Iterator[Connection]:
        with connection.begin_nested():
            yield connection

    app = create_app()
    app.dependency_overrides[get_connection] = override
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
