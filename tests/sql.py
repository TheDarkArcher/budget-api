"""SQL helpers shared by tests that read and write the database directly."""

from typing import Any

from sqlalchemy import Connection, text


def one(connection: Connection, sql: str, **params: object) -> Any:
    """Run a query that returns exactly one value, and return it."""
    return connection.execute(text(sql), params).scalar_one()


def count(connection: Connection, sql: str, **params: object) -> int:
    """Run a ``SELECT count(*)`` query and return the count."""
    result: int = one(connection, sql, **params)
    return result


def rows(connection: Connection, sql: str, **params: object) -> set[tuple[Any, ...]]:
    """Run a query and return its rows as a set of tuples, ignoring order."""
    return {tuple(row) for row in connection.execute(text(sql), params)}


def run(connection: Connection, sql: str, **params: object) -> None:
    """Run a statement whose result isn't needed."""
    connection.execute(text(sql), params)
