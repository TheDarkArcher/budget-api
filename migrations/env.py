"""Alembic environment: runs migrations against the app's database."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine
from sqlalchemy.pool import NullPool

from app.database.engine import get_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations_offline() -> None:
    """Write the migrations' SQL to standard output instead of running it."""
    context.configure(
        url=get_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    """Run the migrations on an open connection, in one transaction.

    Args:
        connection: The database connection to migrate.
    """
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against the database.

    Uses the connection in ``config.attributes["connection"]`` if one was
    passed in, as the tests do; otherwise connects using the settings.
    """
    connection = config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
        return
    with create_engine(get_database_url(), poolclass=NullPool).connect() as conn:
        run_migrations(conn)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
