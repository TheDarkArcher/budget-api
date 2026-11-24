"""Shared fixtures: Postgres container, migrations, test client and fakes."""

from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fakes import (
    FakeItemCategoryRepository,
    FakeTransactionCategoryRepository,
    FakeUserRepository,
)
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from records import World, make_world
from sqlalchemy import Connection, Engine
from testcontainers.community.postgres import PostgresContainer

from app.api import v1
from app.core.config import Settings, get_settings
from app.core.dummy_user import DUMMY_USER_ID, DUMMY_USER_NAME
from app.database.engine import get_engine, get_ping_engine
from app.main import create_app
from app.repositories.users import SQLUserRepository

# Pytest only explains failed asserts in test modules and those registered here.
pytest.register_assert_rewrite("problems")

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
def probe_router(monkeypatch: pytest.MonkeyPatch) -> APIRouter:
    # The real v1 router with a copy of its routes, which monkeypatch swaps
    # back after the test, so probe routes added to it don't leak.
    monkeypatch.setattr(v1.router, "routes", list(v1.router.routes))
    return v1.router


@pytest.fixture
def make_app(connection: Connection) -> Callable[[], FastAPI]:
    # A savepoint per request, so the request's writes are kept or rolled
    # back as open_connection's transaction does.
    @contextmanager
    def open_savepoint() -> Generator[Connection]:
        with connection.begin_nested():
            yield connection

    # Probe fixtures call this after adding their routes, as the app copies
    # the router's routes when it's built.
    def build() -> FastAPI:
        return create_app(open_connection=open_savepoint)

    return build


@pytest.fixture
def app(make_app: Callable[[], FastAPI]) -> FastAPI:
    return make_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def dummy_user(connection: Connection) -> None:
    SQLUserRepository(connection).create(DUMMY_USER_ID, DUMMY_USER_NAME)


@pytest.fixture
def alice(connection: Connection) -> World:
    return make_world(connection, "Alice")


@pytest.fixture
def fake_item_category_repo() -> FakeItemCategoryRepository:
    return FakeItemCategoryRepository()


@pytest.fixture
def fake_transaction_category_repo() -> FakeTransactionCategoryRepository:
    return FakeTransactionCategoryRepository()


@pytest.fixture
def fake_user_repo() -> FakeUserRepository:
    return FakeUserRepository()
