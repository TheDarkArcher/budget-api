"""Tests for the database schema: constraints, cascades, the view and triggers.

Every test runs inside the per-test transaction from conftest.py, so nothing
it writes outlives the test. Statements expected to fail run inside a
savepoint, so the failure doesn't abort the rest of the test.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from psycopg import errors
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError


@dataclass
class World:
    """One user's data: a category linked to an item category, and so on."""

    user: UUID
    category: UUID
    item_category: UUID
    payee: UUID
    tag: UUID
    item: UUID
    item_size: UUID


def one(connection: Connection, sql: str, **params: object) -> Any:
    return connection.execute(text(sql), params).scalar_one()


def count(connection: Connection, table_sql: str, **params: object) -> int:
    result: int = one(connection, table_sql, **params)
    return result


def run(connection: Connection, sql: str, **params: object) -> None:
    connection.execute(text(sql), params)


def fails(
    connection: Connection, error: type[Exception], sql: str, **params: object
) -> None:
    with pytest.raises(DBAPIError) as caught, connection.begin_nested():
        connection.execute(text(sql), params)
    assert isinstance(caught.value.orig, error), caught.value.orig


def make_world(connection: Connection, name: str) -> World:
    user = one(
        connection,
        "INSERT INTO users (name) VALUES (:name) RETURNING id",
        name=name,
    )
    category = one(
        connection,
        "INSERT INTO transaction_categories (user_id, name, type)"
        " VALUES (:user, 'Groceries', 'expense') RETURNING id",
        user=user,
    )
    item_category = one(
        connection,
        "INSERT INTO item_categories (user_id, name)"
        " VALUES (:user, 'Food & Drink') RETURNING id",
        user=user,
    )
    run(
        connection,
        "INSERT INTO transaction_category_item_categories"
        " (transaction_category_id, item_category_id)"
        " VALUES (:category, :item_category)",
        category=category,
        item_category=item_category,
    )
    payee = one(
        connection,
        "INSERT INTO payees (user_id, name) VALUES (:user, 'Supermarket') RETURNING id",
        user=user,
    )
    tag = one(
        connection,
        "INSERT INTO tags (user_id, name) VALUES (:user, 'Dairy') RETURNING id",
        user=user,
    )
    item = one(
        connection,
        "INSERT INTO items (user_id, name, item_category_id)"
        " VALUES (:user, 'Milk', :item_category) RETURNING id",
        user=user,
        item_category=item_category,
    )
    item_size = one(
        connection,
        "INSERT INTO item_sizes (item_id, size_value, size_unit)"
        " VALUES (:item, 2, 'L') RETURNING id",
        item=item,
    )
    run(
        connection,
        "INSERT INTO item_tags (item_id, tag_id) VALUES (:item, :tag)",
        item=item,
        tag=tag,
    )
    return World(user, category, item_category, payee, tag, item, item_size)


def add_transaction(connection: Connection, world: World, *totals: str) -> UUID:
    transaction: UUID = one(
        connection,
        "INSERT INTO transactions"
        " (user_id, occurred_on, transaction_category_id, payee_id)"
        " VALUES (:user, '2026-10-23', :category, :payee) RETURNING id",
        user=world.user,
        category=world.category,
        payee=world.payee,
    )
    for total in totals:
        run(
            connection,
            "INSERT INTO transaction_lines"
            " (transaction_id, item_size_id, quantity, line_total)"
            " VALUES (:transaction, :item_size, 1, :total)",
            transaction=transaction,
            item_size=world.item_size,
            total=Decimal(total),
        )
    return transaction


@pytest.fixture
def alice(connection: Connection) -> World:
    return make_world(connection, "Alice")


@pytest.fixture
def bob(connection: Connection) -> World:
    return make_world(connection, "Bob")


# Keys and defaults


def test_ids_are_uuid_v7_and_timestamps_default(
    connection: Connection, alice: World
) -> None:
    row = connection.execute(
        text("SELECT id, created_at, updated_at FROM users WHERE id = :id"),
        {"id": alice.user},
    ).one()
    assert row.id.version == 7
    assert row.created_at == row.updated_at


# User matching: composite foreign keys for direct links between user-owned
# tables, triggers for transitive links. Never reference another user's data


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
    transaction = add_transaction(connection, alice, "1.00")
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
    transaction = add_transaction(connection, bob, "1.00")
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
    transaction = add_transaction(connection, alice, "1.00")
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


# Immutable user ownership


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
    ids = vars(alice) | {"transaction": add_transaction(connection, alice, "1.00")}
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


# CHECK constraints


@pytest.mark.parametrize(
    ("quantity", "line_total"),
    [("0", "1.00"), ("-1", "1.00"), ("1", "0"), ("1", "-0.01")],
)
def test_rejects_non_positive_quantities_and_totals(
    connection: Connection, alice: World, quantity: str, line_total: str
) -> None:
    transaction = add_transaction(connection, alice, "1.00")
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
    fails(
        connection,
        errors.CheckViolation,
        sql,
        user=alice.user,
        name=name,
        item_category=alice.item_category,
    )


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


# Case-insensitive uniqueness


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
    other_item = one(
        connection,
        "INSERT INTO items (user_id, name, item_category_id)"
        " VALUES (:user, 'Juice', :item_category) RETURNING id",
        user=alice.user,
        item_category=alice.item_category,
    )
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


# Cascades and restricts. A refused ON DELETE RESTRICT is reported as
# RestrictViolation (23001), not ForeignKeyViolation (23503).


def test_deleting_a_transaction_deletes_its_lines(
    connection: Connection, alice: World
) -> None:
    transaction = add_transaction(connection, alice, "1.00", "2.00")
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


def test_deleting_a_category_removes_its_links(
    connection: Connection, alice: World
) -> None:
    run(
        connection,
        "DELETE FROM transaction_categories WHERE id = :id",
        id=alice.category,
    )
    links = count(
        connection,
        "SELECT count(*) FROM transaction_category_item_categories"
        " WHERE item_category_id = :id",
        id=alice.item_category,
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
    item_category = one(
        connection,
        "INSERT INTO item_categories (user_id, name)"
        " VALUES (:user, 'Household') RETURNING id",
        user=alice.user,
    )
    run(
        connection,
        "INSERT INTO transaction_category_item_categories"
        " (transaction_category_id, item_category_id)"
        " VALUES (:category, :item_category)",
        category=alice.category,
        item_category=item_category,
    )
    run(connection, "DELETE FROM item_categories WHERE id = :id", id=item_category)
    links = count(
        connection,
        "SELECT count(*) FROM transaction_category_item_categories"
        " WHERE item_category_id = :id",
        id=item_category,
    )
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
    add_transaction(connection, alice, "1.00")
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


# transaction_totals view


def test_view_derives_total_and_line_count(
    connection: Connection, alice: World
) -> None:
    transaction = add_transaction(connection, alice, "3.50", "2.70")
    row = connection.execute(
        text("SELECT total, line_count FROM transaction_totals WHERE id = :id"),
        {"id": transaction},
    ).one()
    assert row.total == Decimal("6.20")
    assert row.line_count == 2


def test_view_shows_transactions_without_lines(
    connection: Connection, alice: World
) -> None:
    transaction = add_transaction(connection, alice)
    row = connection.execute(
        text("SELECT total, line_count FROM transaction_totals WHERE id = :id"),
        {"id": transaction},
    ).one()
    assert row.total == 0
    assert row.line_count == 0


# items_information view


def test_items_information_has_one_row_per_size_with_all_tags(
    connection: Connection, alice: World
) -> None:
    run(
        connection,
        "INSERT INTO item_sizes (item_id, size_value, size_unit)"
        " VALUES (:item, 1.5, 'L')",
        item=alice.item,
    )
    tag = one(
        connection,
        "INSERT INTO tags (user_id, name) VALUES (:user, 'Breakfast') RETURNING id",
        user=alice.user,
    )
    run(
        connection,
        "INSERT INTO item_tags (item_id, tag_id) VALUES (:item, :tag)",
        item=alice.item,
        tag=tag,
    )
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


# updated_at trigger


def test_updates_set_updated_at(connection: Connection, alice: World) -> None:
    past = datetime(2000, 1, 1, tzinfo=UTC)
    run(
        connection,
        "UPDATE payees SET created_at = :past, updated_at = :past WHERE id = :id",
        past=past,
        id=alice.payee,
    )
    row = connection.execute(
        text("SELECT created_at, updated_at, now() AS now FROM payees WHERE id = :id"),
        {"id": alice.payee},
    ).one()
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
