"""Tests for translating refused database writes into domain errors."""

from dataclasses import dataclass
from uuid import UUID

import pytest
from records import (
    World,
    add_line,
    add_payee,
    add_transaction,
    add_transaction_category,
    link,
)
from sql import one, run
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    ArchivedError,
    Blocker,
    DomainError,
    InUseError,
    NameConflictError,
    TypeChangeError,
)
from app.repositories.sql_errors import translate_sql_constraint_errors

DUPLICATE_NAMES = [
    pytest.param(
        "INSERT INTO transaction_categories (user_id, name, type)"
        " VALUES (:user, 'GROCERIES', 'expense')",
        id="transaction category",
    ),
    pytest.param(
        "INSERT INTO item_categories (user_id, name) VALUES (:user, 'FOOD & DRINK')",
        id="item category",
    ),
    pytest.param(
        "INSERT INTO payees (user_id, name) VALUES (:user, 'SUPERMARKET')",
        id="payee",
    ),
    pytest.param(
        "INSERT INTO tags (user_id, name) VALUES (:user, 'DAIRY')",
        id="tag",
    ),
    pytest.param(
        "INSERT INTO items (user_id, name, item_category_id)"
        " VALUES (:user, 'MILK', :item_category)",
        id="item",
    ),
]
DELETES_IN_USE = [
    pytest.param(
        "DELETE FROM transaction_categories WHERE id = :id",
        "category",
        Blocker.TRANSACTION,
        id="transaction category used by a transaction",
    ),
    pytest.param(
        "DELETE FROM payees WHERE id = :id",
        "payee",
        Blocker.TRANSACTION,
        id="payee used by a transaction",
    ),
    pytest.param(
        "DELETE FROM items WHERE id = :id",
        "item",
        Blocker.TRANSACTION,
        id="item used by a transaction",
    ),
    pytest.param(
        "DELETE FROM item_categories WHERE id = :id",
        "item_category",
        Blocker.ITEM,
        id="item category used by an item",
    ),
    pytest.param(
        "DELETE FROM transaction_categories WHERE id = :id",
        "linked_category",
        Blocker.ITEM_CATEGORY,
        id="transaction category linked to an active item category",
    ),
]
ARCHIVED_CHANGES = [
    pytest.param(
        "UPDATE payees SET name = 'Corner Store' WHERE id = :id",
        "archived_payee",
        id="edit an archived record",
    ),
    pytest.param(
        "DELETE FROM transaction_category_item_categories"
        " WHERE transaction_category_id = :id",
        "archived_category",
        id="change a link of an archived category",
    ),
]


@dataclass
class Refusals:
    """The rows Alice's world lacks, added so particular writes are refused."""

    linked_category: UUID
    archived_category: UUID
    archived_payee: UUID


def translated_error(connection: Connection, sql: str, **params: object) -> DomainError:
    with (
        pytest.raises(DomainError) as caught,
        translate_sql_constraint_errors(connection),
    ):
        run(connection, sql, **params)
    return caught.value


@pytest.fixture
def refusals(connection: Connection, alice: World) -> Refusals:
    linked_category = add_transaction_category(connection, alice.user, "Bills")
    archived_category = add_transaction_category(connection, alice.user, "Rent")
    for category in (linked_category, archived_category):
        link(connection, category, alice.item_category)
    # Archived after linking, as a link can't be added to an archived category.
    run(
        connection,
        "UPDATE transaction_categories SET archived_at = now() WHERE id = :id",
        id=archived_category,
    )
    archived_payee = add_payee(connection, alice.user, "Market", archived=True)
    # Uses the category, the payee and, through its line, the item's size.
    transaction = add_transaction(connection, alice.user, alice.category, alice.payee)
    add_line(connection, transaction, alice.item_size, "3.50")
    return Refusals(linked_category, archived_category, archived_payee)


@pytest.mark.parametrize("sql", DUPLICATE_NAMES)
def test_duplicate_name_is_a_name_conflict(
    connection: Connection, alice: World, sql: str
) -> None:
    error = translated_error(connection, sql, **vars(alice))
    assert type(error) is NameConflictError


@pytest.mark.parametrize(("sql", "record", "blocker"), DELETES_IN_USE)
def test_refused_delete_is_in_use_by_what_blocks_it(
    connection: Connection,
    alice: World,
    refusals: Refusals,
    sql: str,
    record: str,
    blocker: Blocker,
) -> None:
    ids = vars(alice) | vars(refusals)
    error = translated_error(connection, sql, id=ids[record])
    assert isinstance(error, InUseError)
    assert error.blocked_by is blocker


def test_changed_transaction_category_type_is_a_type_change(
    connection: Connection, alice: World
) -> None:
    error = translated_error(
        connection,
        "UPDATE transaction_categories SET type = 'income' WHERE id = :id",
        id=alice.category,
    )
    assert type(error) is TypeChangeError


@pytest.mark.parametrize(("sql", "record"), ARCHIVED_CHANGES)
def test_refused_change_while_archived_is_archived(
    connection: Connection, refusals: Refusals, sql: str, record: str
) -> None:
    error = translated_error(connection, sql, id=vars(refusals)[record])
    assert type(error) is ArchivedError


def test_unmapped_constraint_is_raised_unchanged(
    connection: Connection, alice: World
) -> None:
    with (
        pytest.raises(IntegrityError),
        translate_sql_constraint_errors(connection),
    ):
        run(
            connection,
            "UPDATE item_sizes SET size_value = 3 WHERE id = :id",
            id=alice.item_size,
        )


def test_database_transaction_is_usable_after_a_translated_error(
    connection: Connection, alice: World
) -> None:
    translated_error(
        connection,
        "INSERT INTO payees (user_id, name) VALUES (:user, 'supermarket')",
        user=alice.user,
    )
    found = one(
        connection,
        "SELECT id FROM payees WHERE user_id = :user AND lower(name) = 'supermarket'",
        user=alice.user,
    )
    assert found == alice.payee
