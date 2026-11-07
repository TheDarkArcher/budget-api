"""Tests for the Alembic migrations."""

from collections.abc import Callable, Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, make_url, text
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

# Everything a migration can create in the public schema, apart from Alembic's
# own table. Indexes, constraints and triggers go with their tables.
SCHEMA_OBJECTS = text("""
    SELECT 'relation ' || relname FROM pg_class
    WHERE relnamespace = 'public'::regnamespace
        AND relkind IN ('r', 'p', 'v', 'm', 'S', 'f', 'c')
        AND relname != 'alembic_version'
    UNION ALL
    SELECT 'type ' || typname FROM pg_type
    WHERE typnamespace = 'public'::regnamespace AND typtype IN ('e', 'd', 'r', 'm')
    UNION ALL
    SELECT 'function ' || proname FROM pg_proc
    WHERE pronamespace = 'public'::regnamespace
""")


@pytest.fixture
def scratch_engine(postgres: PostgresContainer) -> Iterator[Engine]:
    url = make_url(postgres.get_connection_url()).set(drivername="postgresql+psycopg")
    admin = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        connection.execute(text("CREATE DATABASE round_trip"))
    engine = create_engine(url.set(database="round_trip"), poolclass=NullPool)
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text("DROP DATABASE round_trip WITH (FORCE)"))


def test_round_trip(
    scratch_engine: Engine, alembic_config: Callable[[Connection], Config]
) -> None:
    with scratch_engine.begin() as connection:
        config = alembic_config(connection)
        head = ScriptDirectory.from_config(config).get_current_head()
        version = text("SELECT version_num FROM alembic_version")

        command.upgrade(config, "head")
        assert connection.execute(version).scalar() == head
        assert connection.execute(SCHEMA_OBJECTS).scalars().all()
        command.downgrade(config, "base")
        assert connection.execute(version).scalar() is None
        assert connection.execute(SCHEMA_OBJECTS).scalars().all() == []
        command.upgrade(config, "head")
        assert connection.execute(version).scalar() == head
