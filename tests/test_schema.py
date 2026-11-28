"""Tests for the database schema: constraints, cascades, the view and triggers.

Every test runs inside the per-test transaction from conftest.py, so nothing
it writes outlives the test. Statements expected to fail run inside a
savepoint, so the failure doesn't abort the rest of the test.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from psycopg import errors
from records import (
    World,
    add_item,
    add_item_category,
    add_line,
    add_size,
    add_tag,
    add_transaction,
    add_transaction_category,
    add_user,
    link,
    make_world,
    tag_item,
)
from sql import count, one, one_row, run
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

# ============================
# |   Helpers and fixtures   |
# ============================


# Statements for each archivable record, keyed by what they do; "record" is
# the World attribute holding its id. An item size has no column that may
# change, so its edit changes the value, which the archived check must refuse
# before the size check does.
ARCHIVABLE_RECORDS = [
    pytest.param(
        {
            "record": "category",
            "archive": "UPDATE transaction_categories SET archived_at = now()"
            " WHERE id = :id",
            "unarchive": "UPDATE transaction_categories SET archived_at = NULL"
            " WHERE id = :id",
            "edit": "UPDATE transaction_categories SET name = 'Rent' WHERE id = :id",
            "unarchive_and_edit": "UPDATE transaction_categories"
            " SET archived_at = NULL, name = 'Rent' WHERE id = :id",
        },
        id="transaction category",
    ),
    pytest.param(
        {
            "record": "item_category",
            "archive": "UPDATE item_categories SET archived_at = now() WHERE id = :id",
            "unarchive": "UPDATE item_categories SET archived_at = NULL WHERE id = :id",
            "edit": "UPDATE item_categories SET name = 'Household' WHERE id = :id",
            "unarchive_and_edit": "UPDATE item_categories"
            " SET archived_at = NULL, name = 'Household' WHERE id = :id",
        },
        id="item category",
    ),
    pytest.param(
        {
            "record": "payee",
            "archive": "UPDATE payees SET archived_at = now() WHERE id = :id",
            "unarchive": "UPDATE payees SET archived_at = NULL WHERE id = :id",
            "edit": "UPDATE payees SET name = 'Corner Store' WHERE id = :id",
            "unarchive_and_edit": "UPDATE payees"
            " SET archived_at = NULL, name = 'Corner Store' WHERE id = :id",
        },
        id="payee",
    ),
    pytest.param(
        {
            "record": "item",
            "archive": "UPDATE items SET archived_at = now() WHERE id = :id",
            "unarchive": "UPDATE items SET archived_at = NULL WHERE id = :id",
            "edit": "UPDATE items SET name = 'Juice' WHERE id = :id",
            "unarchive_and_edit": "UPDATE items"
            " SET archived_at = NULL, name = 'Juice' WHERE id = :id",
        },
        id="item",
    ),
    pytest.param(
        {
            "record": "item_size",
            "archive": "UPDATE item_sizes SET archived_at = now() WHERE id = :id",
            "unarchive": "UPDATE item_sizes SET archived_at = NULL WHERE id = :id",
            "edit": "UPDATE item_sizes SET size_value = 3 WHERE id = :id",
            "unarchive_and_edit": "UPDATE item_sizes"
            " SET archived_at = NULL, size_value = 3 WHERE id = :id",
        },
        id="item size",
    ),
]

# Archiving either side of Alice's link, and changing that link.
ARCHIVE_TRANSACTION_CATEGORY = (
    "UPDATE transaction_categories SET archived_at = now() WHERE id = :category"
)
ARCHIVE_ITEM_CATEGORY = (
    "UPDATE item_categories SET archived_at = now() WHERE id = :item_category"
)
ARCHIVE_LINKED_CATEGORY = [
    pytest.param(ARCHIVE_TRANSACTION_CATEGORY, id="transaction category archived"),
    pytest.param(ARCHIVE_ITEM_CATEGORY, id="item category archived"),
]
# Archiving one side of Alice's link, named by its key in add_unlinked_categories.
ARCHIVED_SIDE = [
    pytest.param(
        ARCHIVE_TRANSACTION_CATEGORY, "category", id="transaction category archived"
    ),
    pytest.param(ARCHIVE_ITEM_CATEGORY, "item_category", id="item category archived"),
]
INSERT_LINK = (
    "INSERT INTO transaction_category_item_categories"
    " (transaction_category_id, item_category_id)"
    " VALUES (:category, :item_category)"
)
ARCHIVE_LINK = (
    "UPDATE transaction_category_item_categories SET archived_at = now()"
    " WHERE transaction_category_id = :category"
    " AND item_category_id = :item_category"
)
UNARCHIVE_LINK = (
    "UPDATE transaction_category_item_categories SET archived_at = NULL"
    " WHERE transaction_category_id = :category"
    " AND item_category_id = :item_category"
)
CHANGE_LINK = [
    pytest.param(ARCHIVE_LINK, id="update"),
    pytest.param(
        "DELETE FROM transaction_category_item_categories"
        " WHERE transaction_category_id = :category"
        " AND item_category_id = :item_category",
        id="delete",
    ),
]


def fails(
    connection: Connection,
    error: type[Exception],
    sql: str,
    *,
    constraint: str | None = None,
    **params: object,
) -> None:
    with pytest.raises(DBAPIError) as caught, connection.begin_nested():
        connection.execute(text(sql), params)
    assert isinstance(caught.value.orig, error), caught.value.orig
    if constraint is not None:
        assert isinstance(caught.value.orig, errors.Error)
        assert caught.value.orig.diag.constraint_name == constraint


def add_world_transaction(connection: Connection, world: World, *totals: str) -> UUID:
    transaction = add_transaction(connection, world.user, world.category, world.payee)
    for total in totals:
        add_line(connection, transaction, world.item_size, total)
    return transaction


def add_unlinked_categories(connection: Connection, user: UUID) -> dict[str, UUID]:
    return {
        "category": add_transaction_category(connection, user, "Rent"),
        "item_category": add_item_category(connection, user, "Household"),
    }


def delete_world(connection: Connection, world: World) -> None:
    # Children first; items take their sizes and tag links with them, and item
    # categories their links, so the transaction category is left unlinked.
    run(connection, "DELETE FROM items WHERE user_id = :user", user=world.user)
    run(
        connection, "DELETE FROM item_categories WHERE user_id = :user", user=world.user
    )
    run(
        connection,
        "DELETE FROM transaction_categories WHERE user_id = :user",
        user=world.user,
    )
    run(connection, "DELETE FROM tags WHERE user_id = :user", user=world.user)
    run(connection, "DELETE FROM payees WHERE user_id = :user", user=world.user)
    run(connection, "DELETE FROM users WHERE id = :user", user=world.user)


def item_category_links_count(connection: Connection, item_category: UUID) -> int:
    return count(
        connection,
        "SELECT count(*) FROM transaction_category_item_categories"
        " WHERE item_category_id = :item_category",
        item_category=item_category,
    )


def transaction_category_links_count(connection: Connection, category: UUID) -> int:
    return count(
        connection,
        "SELECT count(*) FROM transaction_category_item_categories"
        " WHERE transaction_category_id = :category",
        category=category,
    )


def add_link(engine: Engine, category: UUID, item_category: UUID) -> None:
    with engine.begin() as connection:
        run(connection, INSERT_LINK, category=category, item_category=item_category)


def delete_transaction_category(engine: Engine, category: UUID) -> None:
    with engine.begin() as connection:
        run(
            connection,
            "DELETE FROM transaction_categories WHERE id = :id",
            id=category,
        )


def wait_until_blocked(connection: Connection, query: str) -> None:
    # Statistics are read once per transaction, so each check ends its own.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        blocked = one(
            connection,
            "SELECT EXISTS (SELECT FROM pg_stat_activity"
            " WHERE datname = current_database()"
            " AND wait_event_type = 'Lock' AND query LIKE :query)",
            query=query,
        )
        connection.rollback()
        if blocked:
            return
        time.sleep(0.05)
    pytest.fail(f"no statement like {query!r} was blocked")


@pytest.fixture
def bob(connection: Connection) -> World:
    return make_world(connection, "Bob")


# =========================
# |   Keys and defaults   |
# =========================


def test_ids_are_uuid_v7_and_timestamps_default(
    connection: Connection, alice: World
) -> None:
    row = one_row(
        connection,
        "SELECT id, created_at, updated_at FROM users WHERE id = :id",
        id=alice.user,
    )
    assert row.id.version == 7
    assert row.created_at == row.updated_at


# =====================
# |   User matching   |
# =====================


# Composite foreign keys for direct links between user-owned tables,
# triggers for transitive links. Never reference another user's data.


# Each case names the World attributes it binds from Alice as :<name> and
# from Bob as :other_<name>.
@pytest.mark.parametrize(
    ("sql", "own", "other"),
    [
        pytest.param(
            "INSERT INTO transaction_category_item_categories"
            " (transaction_category_id, item_category_id)"
            " VALUES (:category, :other_item_category)",
            ("category",),
            ("item_category",),
            id="category link to other user's item category",
        ),
        pytest.param(
            "INSERT INTO transaction_category_item_categories"
            " (transaction_category_id, item_category_id)"
            " VALUES (:other_category, :item_category)",
            ("item_category",),
            ("category",),
            id="category link to other user's transaction category",
        ),
        pytest.param(
            "INSERT INTO items (user_id, name, item_category_id)"
            " VALUES (:user, 'Bread', :other_item_category)",
            (),
            ("item_category",),
            id="item in other user's item category",
        ),
        pytest.param(
            "INSERT INTO item_tags (item_id, tag_id) VALUES (:item, :other_tag)",
            ("item",),
            ("tag",),
            id="item tagged with other user's tag",
        ),
        pytest.param(
            "INSERT INTO item_tags (item_id, tag_id) VALUES (:other_item, :tag)",
            ("tag",),
            ("item",),
            id="other user's item tagged",
        ),
        pytest.param(
            "INSERT INTO transactions"
            " (user_id, occurred_on, transaction_category_id, payee_id)"
            " VALUES (:user, '2026-10-23', :category, :other_payee)",
            ("category",),
            ("payee",),
            id="transaction with other user's payee",
        ),
        pytest.param(
            "INSERT INTO transactions"
            " (user_id, occurred_on, transaction_category_id, payee_id)"
            " VALUES (:user, '2026-10-23', :other_category, :payee)",
            ("payee",),
            ("category",),
            id="transaction in other user's category",
        ),
    ],
)
def test_rejects_references_to_another_users_data(
    connection: Connection,
    alice: World,
    bob: World,
    sql: str,
    own: tuple[str, ...],
    other: tuple[str, ...],
) -> None:
    params = {name: getattr(alice, name) for name in own} | {
        f"other_{name}": getattr(bob, name) for name in other
    }
    fails(connection, errors.ForeignKeyViolation, sql, user=alice.user, **params)


def test_rejects_line_for_another_users_item(
    connection: Connection, alice: World, bob: World
) -> None:
    transaction = add_world_transaction(connection, alice, "1.00")
    fails(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO transaction_lines"
        " (transaction_id, item_size_id, quantity, line_total)"
        " VALUES (:transaction, :item_size, 1, 1)",
        transaction=transaction,
        item_size=bob.item_size,
    )


def test_rejects_line_in_another_users_transaction(
    connection: Connection, alice: World, bob: World
) -> None:
    transaction = add_world_transaction(connection, bob, "1.00")
    fails(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO transaction_lines"
        " (transaction_id, item_size_id, quantity, line_total)"
        " VALUES (:transaction, :item_size, 1, 1)",
        transaction=transaction,
        item_size=alice.item_size,
    )


def test_rejects_changing_a_reference_to_another_users_data(
    connection: Connection, alice: World, bob: World
) -> None:
    transaction = add_world_transaction(connection, alice, "1.00")
    fails(
        connection,
        errors.ForeignKeyViolation,
        "UPDATE transactions SET payee_id = :payee WHERE id = :id",
        payee=bob.payee,
        id=transaction,
    )
    fails(
        connection,
        errors.ForeignKeyViolation,
        "UPDATE transaction_lines SET item_size_id = :item_size"
        " WHERE transaction_id = :id",
        item_size=bob.item_size,
        id=transaction,
    )


def test_rejects_references_to_missing_rows(
    connection: Connection, alice: World
) -> None:
    fails(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO items (user_id, name, item_category_id)"
        " VALUES (:user, 'Bread', :item_category)",
        user=alice.user,
        item_category=uuid4(),
    )


@pytest.mark.parametrize(
    "name",
    [
        "items_user_id_item_category_id_fkey",
        "transactions_user_id_transaction_category_id_fkey",
        "transactions_user_id_payee_id_fkey",
    ],
)
def test_direct_links_use_composite_foreign_keys(
    connection: Connection, name: str
) -> None:
    columns = one(
        connection,
        "SELECT cardinality(conkey) FROM pg_constraint"
        " WHERE contype = 'f' AND conname = :name",
        name=name,
    )
    assert columns == 2


# ================================
# |   Immutable user ownership   |
# ================================


@pytest.mark.parametrize(
    ("sql", "attribute"),
    [
        pytest.param(
            "UPDATE transaction_categories SET user_id = :user WHERE id = :id",
            "category",
            id="transaction category",
        ),
        pytest.param(
            "UPDATE item_categories SET user_id = :user WHERE id = :id",
            "item_category",
            id="item category",
        ),
        pytest.param(
            "UPDATE payees SET user_id = :user WHERE id = :id", "payee", id="payee"
        ),
        pytest.param("UPDATE tags SET user_id = :user WHERE id = :id", "tag", id="tag"),
        pytest.param(
            "UPDATE items SET user_id = :user WHERE id = :id", "item", id="item"
        ),
        pytest.param(
            "UPDATE transactions SET user_id = :user WHERE id = :id",
            "transaction",
            id="transaction",
        ),
    ],
)
def test_user_ids_cannot_change(
    connection: Connection, alice: World, bob: World, sql: str, attribute: str
) -> None:
    ids = vars(alice) | {
        "transaction": add_world_transaction(connection, alice, "1.00")
    }
    fails(
        connection,
        errors.IntegrityConstraintViolation,
        sql,
        user=bob.user,
        id=ids[attribute],
    )


def test_setting_user_id_to_its_current_value_is_allowed(
    connection: Connection, alice: World
) -> None:
    run(
        connection,
        "UPDATE payees SET user_id = :user WHERE id = :id",
        user=alice.user,
        id=alice.payee,
    )


# =========================
# |   CHECK constraints   |
# =========================


@pytest.mark.parametrize(
    ("quantity", "line_total"),
    [("0", "1.00"), ("-1", "1.00"), ("1", "0"), ("1", "-0.01")],
)
def test_rejects_non_positive_quantities_and_totals(
    connection: Connection, alice: World, quantity: str, line_total: str
) -> None:
    transaction = add_world_transaction(connection, alice, "1.00")
    fails(
        connection,
        errors.CheckViolation,
        "INSERT INTO transaction_lines"
        " (transaction_id, item_size_id, quantity, line_total)"
        " VALUES (:transaction, :item_size, :quantity, :line_total)",
        transaction=transaction,
        item_size=alice.item_size,
        quantity=Decimal(quantity),
        line_total=Decimal(line_total),
    )


@pytest.mark.parametrize("size", ["0", "-2"])
def test_rejects_non_positive_item_sizes(
    connection: Connection, alice: World, size: str
) -> None:
    fails(
        connection,
        errors.CheckViolation,
        "INSERT INTO item_sizes (item_id, size_value, size_unit)"
        " VALUES (:item, :size, 'each')",
        item=alice.item,
        size=Decimal(size),
    )


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users (name) VALUES (:name)",
        "INSERT INTO transaction_categories (user_id, name, type)"
        " VALUES (:user, :name, 'expense')",
        "INSERT INTO item_categories (user_id, name) VALUES (:user, :name)",
        "INSERT INTO payees (user_id, name) VALUES (:user, :name)",
        "INSERT INTO tags (user_id, name) VALUES (:user, :name)",
        "INSERT INTO items (user_id, name, item_category_id)"
        " VALUES (:user, :name, :item_category)",
    ],
)
@pytest.mark.parametrize("name", ["", "   "])
def test_rejects_blank_names(
    connection: Connection, alice: World, sql: str, name: str
) -> None:
    fails(connection, errors.CheckViolation, sql, name=name, **vars(alice))


def test_item_sizes_keep_fractional_values(
    connection: Connection, alice: World
) -> None:
    size = one(
        connection,
        "INSERT INTO item_sizes (item_id, size_value, size_unit)"
        " VALUES (:item, 1.5, 'L') RETURNING size_value",
        item=alice.item,
    )
    assert size == Decimal("1.5")


@pytest.mark.parametrize("unit", ["g", "kg", "mL", "L", "each", "unit", "pack"])
def test_size_units_accept_the_fixed_list(
    connection: Connection, alice: World, unit: str
) -> None:
    run(
        connection,
        "INSERT INTO item_sizes (item_id, size_value, size_unit)"
        " VALUES (:item, 1, :unit)",
        item=alice.item,
        unit=unit,
    )


@pytest.mark.parametrize("unit", ["l", "ml"])
def test_size_units_are_a_fixed_case_sensitive_list(
    connection: Connection, alice: World, unit: str
) -> None:
    fails(
        connection,
        errors.InvalidTextRepresentation,
        "INSERT INTO item_sizes (item_id, size_value, size_unit)"
        " VALUES (:item, 1, :unit)",
        item=alice.item,
        unit=unit,
    )


# ===================================
# |   Case-insensitive uniqueness   |
# ===================================


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO transaction_categories (user_id, name, type)"
        " VALUES (:user, 'GROCERIES', 'expense')",
        "INSERT INTO item_categories (user_id, name) VALUES (:user, 'food & drink')",
        "INSERT INTO payees (user_id, name) VALUES (:user, 'SUPERMARKET')",
        "INSERT INTO tags (user_id, name) VALUES (:user, 'dairy')",
        "INSERT INTO items (user_id, name, item_category_id)"
        " VALUES (:user, 'MILK', :item_category)",
    ],
)
def test_names_are_unique_per_user_ignoring_case(
    connection: Connection, alice: World, bob: World, sql: str
) -> None:
    # Bob already has these names, so they only need to be unique per user.
    fails(
        connection,
        errors.UniqueViolation,
        sql,
        user=alice.user,
        item_category=alice.item_category,
    )


def test_archived_names_still_count_as_taken(
    connection: Connection, alice: World
) -> None:
    run(
        connection,
        "UPDATE payees SET archived_at = now() WHERE id = :id",
        id=alice.payee,
    )
    fails(
        connection,
        errors.UniqueViolation,
        "INSERT INTO payees (user_id, name) VALUES (:user, 'supermarket')",
        user=alice.user,
    )


def test_item_sizes_are_unique_within_an_item(
    connection: Connection, alice: World
) -> None:
    insert = (
        "INSERT INTO item_sizes (item_id, size_value, size_unit)"
        " VALUES (:item, :size, :unit)"
    )
    other_item = add_item(connection, alice.user, alice.item_category, "Juice")
    run(connection, insert, item=alice.item, size=1, unit="L")
    run(connection, insert, item=alice.item, size=2, unit="kg")
    run(connection, insert, item=other_item, size=2, unit="L")
    fails(
        connection,
        errors.UniqueViolation,
        insert,
        item=alice.item,
        size=Decimal("2.000"),
        unit="L",
    )


# ==============================
# |   Cascades and restricts   |
# ==============================


# A refused ON DELETE RESTRICT is reported as RestrictViolation (23001),
# not ForeignKeyViolation (23503).


def test_deleting_a_transaction_deletes_its_lines(
    connection: Connection, alice: World
) -> None:
    transaction = add_world_transaction(connection, alice, "1.00", "2.00")
    run(connection, "DELETE FROM transactions WHERE id = :id", id=transaction)
    lines = count(
        connection,
        "SELECT count(*) FROM transaction_lines WHERE transaction_id = :id",
        id=transaction,
    )
    assert lines == 0


def test_deleting_a_tag_removes_it_from_items(
    connection: Connection, alice: World
) -> None:
    run(connection, "DELETE FROM tags WHERE id = :id", id=alice.tag)
    links = count(
        connection, "SELECT count(*) FROM item_tags WHERE item_id = :id", id=alice.item
    )
    assert links == 0


def test_deleting_an_item_removes_its_tags_and_sizes(
    connection: Connection, alice: World
) -> None:
    run(connection, "DELETE FROM items WHERE id = :id", id=alice.item)
    links = count(
        connection, "SELECT count(*) FROM item_tags WHERE tag_id = :id", id=alice.tag
    )
    sizes = count(
        connection,
        "SELECT count(*) FROM item_sizes WHERE item_id = :id",
        id=alice.item,
    )
    assert links == 0
    assert sizes == 0


def test_deleting_an_item_category_removes_its_links(
    connection: Connection, alice: World
) -> None:
    # A new item category, since one with items can't be deleted.
    item_category = add_item_category(connection, alice.user, "Household")
    link(connection, alice.category, item_category)
    run(connection, "DELETE FROM item_categories WHERE id = :id", id=item_category)
    links = item_category_links_count(connection, item_category)
    assert links == 0


@pytest.mark.parametrize(
    ("sql", "attribute"),
    [
        pytest.param("DELETE FROM payees WHERE id = :id", "payee", id="payee"),
        pytest.param(
            "DELETE FROM transaction_categories WHERE id = :id",
            "category",
            id="category",
        ),
        pytest.param("DELETE FROM items WHERE id = :id", "item", id="item"),
        pytest.param(
            "DELETE FROM item_sizes WHERE id = :id", "item_size", id="item size"
        ),
    ],
)
def test_cannot_delete_records_still_used_by_a_transaction(
    connection: Connection, alice: World, sql: str, attribute: str
) -> None:
    add_world_transaction(connection, alice, "1.00")
    fails(connection, errors.RestrictViolation, sql, id=getattr(alice, attribute))


def test_cannot_delete_an_item_category_that_has_items(
    connection: Connection, alice: World
) -> None:
    fails(
        connection,
        errors.RestrictViolation,
        "DELETE FROM item_categories WHERE id = :id",
        id=alice.item_category,
    )


def test_cannot_delete_a_user_who_owns_data(
    connection: Connection, alice: World
) -> None:
    fails(
        connection,
        errors.RestrictViolation,
        "DELETE FROM users WHERE id = :id",
        id=alice.user,
    )


# =========================
# |   Immutable records   |
# =========================


@pytest.mark.parametrize("statements", ARCHIVABLE_RECORDS)
@pytest.mark.parametrize("change", ["edit", "archive", "unarchive_and_edit"])
def test_archived_records_can_only_be_unarchived(
    connection: Connection, alice: World, statements: dict[str, Any], change: str
) -> None:
    record = getattr(alice, statements["record"])
    run(connection, statements["archive"], id=record)
    fails(
        connection,
        errors.IntegrityConstraintViolation,
        statements[change],
        constraint="archived_record_immutable",
        id=record,
    )


@pytest.mark.parametrize("statements", ARCHIVABLE_RECORDS)
def test_archived_records_can_be_unarchived(
    connection: Connection, alice: World, statements: dict[str, Any]
) -> None:
    record = getattr(alice, statements["record"])
    run(connection, statements["archive"], id=record)
    run(connection, statements["unarchive"], id=record)


def test_transaction_category_type_cannot_change(
    connection: Connection, alice: World
) -> None:
    fails(
        connection,
        errors.IntegrityConstraintViolation,
        "UPDATE transaction_categories SET type = 'income' WHERE id = :id",
        constraint="transaction_categories_type_immutable",
        id=alice.category,
    )


@pytest.mark.parametrize(
    "sql",
    [
        pytest.param("UPDATE item_sizes SET size_value = 3 WHERE id = :id", id="value"),
        pytest.param(
            "UPDATE item_sizes SET size_unit = 'kg' WHERE id = :id", id="unit"
        ),
    ],
)
def test_item_size_value_and_unit_cannot_change(
    connection: Connection, alice: World, sql: str
) -> None:
    # Alice's size is unused, so the refusal doesn't depend on transaction lines.
    fails(
        connection,
        errors.IntegrityConstraintViolation,
        sql,
        constraint="item_sizes_size_immutable",
        id=alice.item_size,
    )


def test_item_size_cannot_move_to_another_item(
    connection: Connection, alice: World
) -> None:
    other_item = add_item(connection, alice.user, alice.item_category, "Juice")
    fails(
        connection,
        errors.IntegrityConstraintViolation,
        "UPDATE item_sizes SET item_id = :item WHERE id = :id",
        constraint="item_sizes_item_id_immutable",
        item=other_item,
        id=alice.item_size,
    )


# ======================
# |   Category links   |
# ======================


# A link can't change while either of its categories is archived, unless
# the change is a category's delete removing it.


@pytest.mark.parametrize("archive", ARCHIVE_LINKED_CATEGORY)
@pytest.mark.parametrize("change", CHANGE_LINK)
def test_links_cannot_change_while_a_category_is_archived(
    connection: Connection, alice: World, archive: str, change: str
) -> None:
    ids = {"category": alice.category, "item_category": alice.item_category}
    run(connection, archive, **ids)
    fails(
        connection,
        errors.IntegrityConstraintViolation,
        change,
        constraint="transaction_category_item_categories_category_archived",
        **ids,
    )


@pytest.mark.parametrize("archive", ARCHIVE_LINKED_CATEGORY)
def test_links_cannot_be_unarchived_while_a_category_is_archived(
    connection: Connection, alice: World, archive: str
) -> None:
    # The link is archived while both categories are active, then one of them
    # is archived.
    ids = {"category": alice.category, "item_category": alice.item_category}
    run(connection, ARCHIVE_LINK, **ids)
    run(connection, archive, **ids)
    fails(
        connection,
        errors.IntegrityConstraintViolation,
        UNARCHIVE_LINK,
        constraint="transaction_category_item_categories_category_archived",
        **ids,
    )


@pytest.mark.parametrize(("archive", "archived_side"), ARCHIVED_SIDE)
def test_links_cannot_be_added_while_a_category_is_archived(
    connection: Connection, alice: World, archive: str, archived_side: str
) -> None:
    # The new link joins the archived one of Alice's categories to a new
    # active category on the other side.
    ids = {"category": alice.category, "item_category": alice.item_category}
    run(connection, archive, **ids)
    new_ids = add_unlinked_categories(connection, alice.user)
    fails(
        connection,
        errors.IntegrityConstraintViolation,
        INSERT_LINK,
        constraint="transaction_category_item_categories_category_archived",
        **new_ids | {archived_side: ids[archived_side]},
    )


@pytest.mark.parametrize(("archive", "archived_side"), ARCHIVED_SIDE)
def test_adding_a_link_during_a_concurrent_archive_is_refused(
    engine: Engine, archive: str, archived_side: str
) -> None:
    # The link's insert starts while the archive isn't committed yet, so it
    # must wait and then see the category as archived, rather than link it.
    with engine.connect() as setup:
        carol = make_world(setup, "Carol")
        new_ids = add_unlinked_categories(setup, carol.user)
        setup.commit()
    ids = {"category": carol.category, "item_category": carol.item_category}
    link_ids = new_ids | {archived_side: ids[archived_side]}
    try:
        # The executor comes first so that, on a failure, the connections close
        # and release the archive's lock before the executor waits for the link.
        with (
            ThreadPoolExecutor(max_workers=1) as executor,
            engine.connect() as archiver,
            engine.connect() as watcher,
        ):
            run(archiver, archive, **ids)
            linking = executor.submit(
                add_link, engine, link_ids["category"], link_ids["item_category"]
            )
            wait_until_blocked(watcher, "INSERT INTO transaction_category_item_%")
            archiver.commit()
            with pytest.raises(DBAPIError) as caught:
                linking.result(timeout=10)
        assert isinstance(caught.value.orig, errors.IntegrityConstraintViolation)
        assert (
            caught.value.orig.diag.constraint_name
            == "transaction_category_item_categories_category_archived"
        )
    finally:
        with engine.connect() as cleanup:
            delete_world(cleanup, carol)
            cleanup.commit()


def test_deleting_a_category_waits_for_a_concurrent_link(engine: Engine) -> None:
    # The delete starts while a link to the category isn't committed yet, so it
    # must wait and then see the link, rather than cascade it away.
    with engine.connect() as setup:
        carol = make_world(setup, "Carol")
        category = add_transaction_category(setup, carol.user, "Rent")
        setup.commit()
    try:
        # The executor comes first so that, on a failure, the connections close
        # and release the link's lock before the executor waits for the delete.
        with (
            ThreadPoolExecutor(max_workers=1) as executor,
            engine.connect() as linker,
            engine.connect() as watcher,
        ):
            run(
                linker,
                INSERT_LINK,
                category=category,
                item_category=carol.item_category,
            )
            deleting = executor.submit(delete_transaction_category, engine, category)
            wait_until_blocked(watcher, "DELETE FROM transaction_categories%")
            linker.commit()
            with pytest.raises(DBAPIError) as caught:
                deleting.result(timeout=10)
        assert isinstance(caught.value.orig, errors.RestrictViolation)
        assert (
            caught.value.orig.diag.constraint_name
            == "transaction_categories_item_category_link"
        )
    finally:
        with engine.connect() as cleanup:
            delete_world(cleanup, carol)
            cleanup.commit()


def test_deleting_an_archived_transaction_category_removes_its_links(
    connection: Connection, alice: World
) -> None:
    run(connection, ARCHIVE_TRANSACTION_CATEGORY, category=alice.category)
    run(
        connection,
        "DELETE FROM transaction_categories WHERE id = :id",
        id=alice.category,
    )
    links = item_category_links_count(connection, alice.item_category)
    assert links == 0


def test_deleting_an_item_category_removes_links_to_archived_categories(
    connection: Connection, alice: World
) -> None:
    item_category = add_item_category(connection, alice.user, "Household")
    link(connection, alice.category, item_category)
    run(connection, ARCHIVE_TRANSACTION_CATEGORY, category=alice.category)
    run(connection, "DELETE FROM item_categories WHERE id = :id", id=item_category)
    links = item_category_links_count(connection, item_category)
    assert links == 0


def test_cannot_delete_an_active_transaction_category_with_an_active_link(
    connection: Connection, alice: World
) -> None:
    fails(
        connection,
        errors.RestrictViolation,
        "DELETE FROM transaction_categories WHERE id = :id",
        constraint="transaction_categories_item_category_link",
        id=alice.category,
    )
    links = transaction_category_links_count(connection, alice.category)
    assert links == 1


@pytest.mark.parametrize(
    "unlink",
    [
        pytest.param(
            "UPDATE transaction_category_item_categories SET archived_at = now()"
            " WHERE transaction_category_id = :category",
            id="link archived",
        ),
        pytest.param(ARCHIVE_ITEM_CATEGORY, id="item category archived"),
    ],
)
def test_a_transaction_category_without_an_applying_link_deletes_with_its_links(
    connection: Connection, alice: World, unlink: str
) -> None:
    run(
        connection,
        unlink,
        category=alice.category,
        item_category=alice.item_category,
    )
    run(
        connection,
        "DELETE FROM transaction_categories WHERE id = :id",
        id=alice.category,
    )
    links = transaction_category_links_count(connection, alice.category)
    assert links == 0


# ========================
# |   Idempotency keys   |
# ========================


def test_idempotency_keys_are_unique_per_user(
    connection: Connection, alice: World, bob: World
) -> None:
    insert = (
        "INSERT INTO idempotency_keys (user_id, key, request_hash)"
        " VALUES (:user, 'abc', 'hash')"
    )
    run(connection, insert, user=alice.user)
    run(connection, insert, user=bob.user)
    fails(
        connection,
        errors.UniqueViolation,
        insert,
        constraint="idempotency_keys_user_id_key_key",
        user=alice.user,
    )


def test_idempotency_keys_without_a_user_are_unique(connection: Connection) -> None:
    insert = (
        "INSERT INTO idempotency_keys (user_id, key, request_hash)"
        " VALUES (NULL, 'abc', 'hash')"
    )
    run(connection, insert)
    fails(
        connection,
        errors.UniqueViolation,
        insert,
        constraint="idempotency_keys_user_id_key_key",
    )


@pytest.mark.parametrize(
    ("status", "body"),
    [
        pytest.param(201, None, id="status without body"),
        pytest.param(None, "{}", id="body without status"),
    ],
)
def test_idempotency_key_responses_are_stored_whole(
    connection: Connection, alice: World, status: int | None, body: str | None
) -> None:
    fails(
        connection,
        errors.CheckViolation,
        "INSERT INTO idempotency_keys"
        " (user_id, key, request_hash, response_status, response_body)"
        " VALUES (:user, 'abc', 'hash', :status, :body)",
        constraint="idempotency_keys_response_complete",
        user=alice.user,
        status=status,
        body=body,
    )


def test_deleting_a_user_removes_their_idempotency_keys(
    connection: Connection,
) -> None:
    user = add_user(connection, "Carol")
    run(
        connection,
        "INSERT INTO idempotency_keys (user_id, key, request_hash)"
        " VALUES (:user, 'abc', 'hash')",
        user=user,
    )
    run(connection, "DELETE FROM users WHERE id = :id", id=user)
    keys = count(
        connection,
        "SELECT count(*) FROM idempotency_keys WHERE user_id = :id",
        id=user,
    )
    assert keys == 0


# ===============================
# |   transaction_totals view   |
# ===============================


def test_view_derives_total_and_line_count(
    connection: Connection, alice: World
) -> None:
    transaction = add_world_transaction(connection, alice, "3.50", "2.70")
    row = one_row(
        connection,
        "SELECT total, line_count FROM transaction_totals WHERE id = :id",
        id=transaction,
    )
    assert row.total == Decimal("6.20")
    assert row.line_count == 2


def test_view_shows_transactions_without_lines(
    connection: Connection, alice: World
) -> None:
    transaction = add_world_transaction(connection, alice)
    row = one_row(
        connection,
        "SELECT total, line_count FROM transaction_totals WHERE id = :id",
        id=transaction,
    )
    assert row.total == 0
    assert row.line_count == 0


# ==============================
# |   items_information view   |
# ==============================


def test_items_information_has_one_row_per_size_with_all_tags(
    connection: Connection, alice: World
) -> None:
    add_size(connection, alice.item, "1.5", "L")
    tag_item(connection, alice.item, add_tag(connection, alice.user, "Breakfast"))
    rows = (
        connection.execute(
            text(
                "SELECT * FROM items_information WHERE item_id = :item"
                " ORDER BY size_value"
            ),
            {"item": alice.item},
        )
        .mappings()
        .all()
    )
    assert [row["size_value"] for row in rows] == [Decimal("1.50"), Decimal("2.00")]
    for row in rows:
        assert row["user_id"] == alice.user
        assert row["name"] == "Milk"
        assert row["item_category_id"] == alice.item_category
        assert row["tags"] == ["Breakfast", "Dairy"]


def test_items_information_leaves_out_archived_tags(
    connection: Connection, alice: World
) -> None:
    run(
        connection,
        "UPDATE tags SET archived_at = now() WHERE id = :id",
        id=alice.tag,
    )
    tags = one(
        connection,
        "SELECT tags FROM items_information WHERE id = :id",
        id=alice.item_size,
    )
    assert tags == []


def test_items_information_shows_sizes_of_untagged_items(
    connection: Connection, alice: World
) -> None:
    run(
        connection,
        "DELETE FROM item_tags WHERE item_id = :item",
        item=alice.item,
    )
    tags = one(
        connection,
        "SELECT tags FROM items_information WHERE id = :id",
        id=alice.item_size,
    )
    assert tags == []


# ==========================
# |   updated_at trigger   |
# ==========================


def test_updates_set_updated_at(connection: Connection, alice: World) -> None:
    past = datetime(2000, 1, 1, tzinfo=UTC)
    run(
        connection,
        "UPDATE payees SET created_at = :past, updated_at = :past WHERE id = :id",
        past=past,
        id=alice.payee,
    )
    row = one_row(
        connection,
        "SELECT created_at, updated_at, now() AS now FROM payees WHERE id = :id",
        id=alice.payee,
    )
    assert row.created_at == past
    assert row.updated_at == row.now


def test_every_table_with_updated_at_has_the_trigger(connection: Connection) -> None:
    tables = connection.execute(
        text("""
            SELECT pg_class.relname AS name, EXISTS (
                SELECT FROM pg_trigger
                WHERE pg_trigger.tgrelid = pg_class.oid
                    AND pg_trigger.tgfoid = 'set_updated_at()'::regprocedure
            ) AS has_trigger
            FROM pg_class
                JOIN pg_attribute ON pg_attribute.attrelid = pg_class.oid
            WHERE pg_class.relnamespace = 'public'::regnamespace
                AND pg_class.relkind IN ('r', 'p')
                AND pg_attribute.attname = 'updated_at'
                AND NOT pg_attribute.attisdropped
        """)
    ).all()
    assert tables
    assert [table.name for table in tables if not table.has_trigger] == []
