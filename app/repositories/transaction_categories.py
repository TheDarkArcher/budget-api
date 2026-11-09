"""SQL for the ``transaction_categories`` table and its item category links."""

from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, text

type CategoryType = Literal["income", "expense"]


def insert(
    connection: Connection, user_id: UUID, name: str, category_type: CategoryType
) -> UUID:
    """Insert a transaction category.

    Args:
        connection: The connection to run the insert on.
        user_id: The id of the user who owns the category.
        name: The category's name.
        category_type: Whether the category is for income or expenses.

    Returns:
        The new category's id.
    """
    category_id: UUID = connection.execute(
        text(
            "INSERT INTO transaction_categories (user_id, name, type)"
            " VALUES (:user_id, :name, :type) RETURNING id"
        ),
        {"user_id": user_id, "name": name, "type": category_type},
    ).scalar_one()
    return category_id


def link_item_category(
    connection: Connection, transaction_category_id: UUID, item_category_id: UUID
) -> None:
    """Allow an item category under a transaction category.

    Args:
        connection: The connection to run the insert on.
        transaction_category_id: The transaction category to link.
        item_category_id: The item category to allow under it.
    """
    connection.execute(
        text(
            "INSERT INTO transaction_category_item_categories"
            " (transaction_category_id, item_category_id)"
            " VALUES (:transaction_category_id, :item_category_id)"
        ),
        {
            "transaction_category_id": transaction_category_id,
            "item_category_id": item_category_id,
        },
    )
