"""Tests for the seed script, against the real database."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest
import seed
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.dummy_user import DUMMY_USER_ID

EXPECTED_TRANSACTION_CATEGORIES = {
    ("Salary", "income"),
    ("Groceries", "expense"),
    ("Rent", "expense"),
    ("Bills", "expense"),
}
EXPECTED_ITEM_CATEGORIES = {
    ("Food & Drink",),
    ("Household",),
    ("Personal Care",),
    ("General / Other",),
}
EXPECTED_LINKS = {
    ("Salary", "General / Other"),
    ("Groceries", "Food & Drink"),
    ("Groceries", "Household"),
    ("Groceries", "Personal Care"),
    ("Rent", "General / Other"),
    ("Bills", "Household"),
    ("Bills", "General / Other"),
}


@dataclass
class SavepointEngine:
    """Stands in for the engine, so nothing the script commits outlives a test.

    Each transaction it begins is a savepoint in the test's connection.
    """

    connection: Connection

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        with self.connection.begin_nested():
            yield self.connection


def rows(connection: Connection, sql: str) -> set[tuple[Any, ...]]:
    return {
        tuple(row) for row in connection.execute(text(sql), {"user": DUMMY_USER_ID})
    }


def dummy_user_data(connection: Connection) -> dict[str, set[tuple[Any, ...]]]:
    return {
        "user": rows(connection, "SELECT name FROM users WHERE id = :user"),
        "transaction categories": rows(
            connection,
            "SELECT name, type::text FROM transaction_categories WHERE user_id = :user",
        ),
        "item categories": rows(
            connection, "SELECT name FROM item_categories WHERE user_id = :user"
        ),
        "links": rows(
            connection,
            "SELECT transaction_categories.name, item_categories.name"
            " FROM transaction_category_item_categories"
            "  JOIN transaction_categories ON transaction_categories.id"
            "   = transaction_category_item_categories.transaction_category_id"
            "  JOIN item_categories ON item_categories.id"
            "   = transaction_category_item_categories.item_category_id"
            " WHERE transaction_categories.user_id = :user",
        ),
    }


@pytest.fixture
def savepoint_engine(connection: Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed, "get_engine", lambda: SavepointEngine(connection))


def test_seeds_the_dummy_user_with_the_default_data(connection: Connection) -> None:
    assert seed.seed_dummy_user(connection) is True
    assert dummy_user_data(connection) == {
        "user": {("Dummy user",)},
        "transaction categories": EXPECTED_TRANSACTION_CATEGORIES,
        "item categories": EXPECTED_ITEM_CATEGORIES,
        "links": EXPECTED_LINKS,
    }


def test_seeding_again_changes_nothing(connection: Connection) -> None:
    seed.seed_dummy_user(connection)
    before = dummy_user_data(connection)
    assert seed.seed_dummy_user(connection) is False
    assert dummy_user_data(connection) == before


@pytest.mark.usefixtures("savepoint_engine")
def test_main_creates_the_dummy_user_then_finds_them(
    connection: Connection, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    assert seed.main() == 0
    assert "Created the dummy user" in caplog.text
    assert dummy_user_data(connection)["user"] == {("Dummy user",)}
    caplog.clear()
    assert seed.main() == 0
    assert "already exists" in caplog.text


@pytest.mark.usefixtures("savepoint_engine")
def test_a_failed_seed_leaves_nothing_behind(
    connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(connection: Connection, user_id: object) -> None:
        raise SQLAlchemyError("provisioning failed")

    # Fails after the user has been inserted, in the same transaction.
    monkeypatch.setattr(seed, "provision_user", fail)
    assert seed.main() == 1
    assert "Seeding failed" in caplog.text
    assert dummy_user_data(connection)["user"] == set()
