"""Database engine and connections."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import URL, Connection, Engine, create_engine, make_url, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

CONNECT_TIMEOUT_SECONDS = 2
PING_TIMEOUT_SECONDS = 2

# Detect a dropped network connection within seconds rather than relying on
# the operating system's TCP defaults, which can take minutes or hours.
KEEPALIVE_ARGS = {
    "keepalives": 1,
    "keepalives_idle": 5,
    "keepalives_interval": 2,
    "keepalives_count": 3,
    "tcp_user_timeout": 10_000,
}


def get_database_url() -> URL:
    """Build the SQLAlchemy URL for the database from the settings.

    Returns:
        The ``DATABASE_URL`` setting with the psycopg 3 driver added.
    """
    return make_url(str(get_settings().database_url.get_secret_value())).set(
        drivername="postgresql+psycopg"
    )


@lru_cache
def get_engine() -> Engine:
    """Create the engine used by requests, once, from the settings.

    Connections wait at most ``database_pool_timeout`` seconds for a free
    pool slot, and each statement runs for at most
    ``database_statement_timeout`` seconds.

    Returns:
        A sync SQLAlchemy engine using the psycopg 3 driver.
    """
    settings = get_settings()
    statement_timeout_ms = settings.database_statement_timeout * 1000
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        pool_timeout=settings.database_pool_timeout,
        connect_args={
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "options": f"-c statement_timeout={statement_timeout_ms}",
            **KEEPALIVE_ARGS,
        },
    )


@lru_cache
def get_ping_engine() -> Engine:
    """Create the engine used by the health check, once.

    It has no connection pool, so a ping stuck on an unresponsive database
    never holds a connection that requests need.

    Returns:
        A sync SQLAlchemy engine using the psycopg 3 driver.
    """
    return create_engine(
        get_database_url(),
        poolclass=NullPool,
        connect_args={"connect_timeout": PING_TIMEOUT_SECONDS, **KEEPALIVE_ARGS},
    )


def get_connection() -> Iterator[Connection]:
    """Provide a connection in a transaction for one request.

    The transaction commits if the request succeeds and rolls back if it
    raises.

    Yields:
        A database connection.
    """
    with get_engine().begin() as connection:
        yield connection


def ping() -> None:
    """Check that the database answers a trivial query.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If the database can't be reached
            or doesn't answer within the timeout.
    """
    with get_ping_engine().connect() as connection:
        connection.execute(
            text("SELECT set_config('statement_timeout', :ms, true)"),
            {"ms": str(PING_TIMEOUT_SECONDS * 1000)},
        )
        connection.execute(text("SELECT 1"))
