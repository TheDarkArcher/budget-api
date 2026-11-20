"""Helpers that insert one record each, for tests that set up rows directly."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sql import one, run
from sqlalchemy import Connection


@dataclass
class World:
    """One user's records, linked together, as ``make_world`` inserts them."""

    user: UUID
    category: UUID
    item_category: UUID
    payee: UUID
    tag: UUID
    item: UUID
    item_size: UUID


def make_world(connection: Connection, name: str) -> World:
    """Insert a user with one of each kind of record except transactions.

    The records are linked together, and their ids are returned.
    """
    user = add_user(connection, name)
    category = add_transaction_category(connection, user, "Groceries")
    item_category = add_item_category(connection, user, "Food & Drink")
    link(connection, category, item_category)
    payee = add_payee(connection, user, "Supermarket")
    tag = add_tag(connection, user, "Dairy")
    item = add_item(connection, user, item_category, "Milk")
    item_size = add_size(connection, item, "2", "L")
    tag_item(connection, item, tag)
    return World(user, category, item_category, payee, tag, item, item_size)


def add_user(connection: Connection, name: str) -> UUID:
    """Insert a user and return their id."""
    user: UUID = one(
        connection, "INSERT INTO users (name) VALUES (:name) RETURNING id", name=name
    )
    return user


def add_transaction_category(
    connection: Connection,
    user: UUID,
    name: str,
    category_type: str = "expense",
    *,
    archived: bool = False,
) -> UUID:
    """Insert a transaction category and return its id."""
    category: UUID = one(
        connection,
        "INSERT INTO transaction_categories (user_id, name, type, archived_at)"
        " VALUES (:user, :name, :type, CASE WHEN :archived THEN now() END)"
        " RETURNING id",
        user=user,
        name=name,
        type=category_type,
        archived=archived,
    )
    return category


def add_item_category(
    connection: Connection, user: UUID, name: str, *, archived: bool = False
) -> UUID:
    """Insert an item category and return its id."""
    item_category: UUID = one(
        connection,
        "INSERT INTO item_categories (user_id, name, archived_at)"
        " VALUES (:user, :name, CASE WHEN :archived THEN now() END)"
        " RETURNING id",
        user=user,
        name=name,
        archived=archived,
    )
    return item_category


def link(connection: Connection, category: UUID, item_category: UUID) -> None:
    """Link a transaction category to an item category."""
    run(
        connection,
        "INSERT INTO transaction_category_item_categories"
        " (transaction_category_id, item_category_id)"
        " VALUES (:category, :item_category)",
        category=category,
        item_category=item_category,
    )


def add_payee(
    connection: Connection, user: UUID, name: str, *, archived: bool = False
) -> UUID:
    """Insert a payee and return its id."""
    payee: UUID = one(
        connection,
        "INSERT INTO payees (user_id, name, archived_at)"
        " VALUES (:user, :name, CASE WHEN :archived THEN now() END)"
        " RETURNING id",
        user=user,
        name=name,
        archived=archived,
    )
    return payee


def add_tag(connection: Connection, user: UUID, name: str) -> UUID:
    """Insert a tag and return its id."""
    tag: UUID = one(
        connection,
        "INSERT INTO tags (user_id, name) VALUES (:user, :name) RETURNING id",
        user=user,
        name=name,
    )
    return tag


def add_item(
    connection: Connection, user: UUID, item_category: UUID, name: str
) -> UUID:
    """Insert an item in an item category and return its id."""
    item: UUID = one(
        connection,
        "INSERT INTO items (user_id, name, item_category_id)"
        " VALUES (:user, :name, :item_category) RETURNING id",
        user=user,
        name=name,
        item_category=item_category,
    )
    return item


def tag_item(connection: Connection, item: UUID, tag: UUID) -> None:
    """Give an item a tag."""
    run(
        connection,
        "INSERT INTO item_tags (item_id, tag_id) VALUES (:item, :tag)",
        item=item,
        tag=tag,
    )


def add_size(connection: Connection, item: UUID, value: str, unit: str) -> UUID:
    """Insert one of an item's sizes and return its id."""
    size: UUID = one(
        connection,
        "INSERT INTO item_sizes (item_id, size_value, size_unit)"
        " VALUES (:item, :value, :unit) RETURNING id",
        item=item,
        value=Decimal(value),
        unit=unit,
    )
    return size


def add_transaction(
    connection: Connection, user: UUID, category: UUID, payee: UUID
) -> UUID:
    """Insert a transaction with no lines and return its id."""
    transaction: UUID = one(
        connection,
        "INSERT INTO transactions"
        " (user_id, occurred_on, transaction_category_id, payee_id)"
        " VALUES (:user, '2026-10-23', :category, :payee) RETURNING id",
        user=user,
        category=category,
        payee=payee,
    )
    return transaction


def add_line(
    connection: Connection,
    transaction: UUID,
    item_size: UUID,
    line_total: str,
    quantity: str = "1",
) -> UUID:
    """Insert a line of a transaction and return its id."""
    line: UUID = one(
        connection,
        "INSERT INTO transaction_lines"
        " (transaction_id, item_size_id, quantity, line_total)"
        " VALUES (:transaction, :item_size, :quantity, :line_total) RETURNING id",
        transaction=transaction,
        item_size=item_size,
        quantity=Decimal(quantity),
        line_total=Decimal(line_total),
    )
    return line
