"""Business rules for users."""

from uuid import UUID

from sqlalchemy import Connection

from app.repositories import item_categories, transaction_categories
from app.repositories.transaction_categories import CategoryType

DEFAULT_TRANSACTION_CATEGORIES: dict[str, CategoryType] = {
    "Salary": "income",
    "Groceries": "expense",
    "Rent": "expense",
    "Bills": "expense",
}

DEFAULT_ITEM_CATEGORIES = (
    "Food & Drink",
    "Household",
    "Personal Care",
    "General / Other",
)

# The item categories allowed under each default transaction category.
DEFAULT_CATEGORY_LINKS: dict[str, tuple[str, ...]] = {
    "Salary": ("General / Other",),
    "Groceries": ("Food & Drink", "Household", "Personal Care"),
    "Rent": ("General / Other",),
    "Bills": ("Household", "General / Other"),
}


def provision_user(connection: Connection, user_id: UUID) -> None:
    """Create a new user's default categories and the links between them.

    Runs on the caller's connection, so it is part of the caller's database
    transaction: if anything fails, none of the defaults are kept.

    Args:
        connection: The connection to write the defaults on, inside a
            transaction.
        user_id: The id of the user to provision, who must already exist.
    """
    item_category_ids = {
        name: item_categories.insert(connection, user_id, name)
        for name in DEFAULT_ITEM_CATEGORIES
    }
    for name, category_type in DEFAULT_TRANSACTION_CATEGORIES.items():
        transaction_category_id = transaction_categories.insert(
            connection, user_id, name, category_type
        )
        for item_category in DEFAULT_CATEGORY_LINKS[name]:
            transaction_categories.link_item_category(
                connection, transaction_category_id, item_category_ids[item_category]
            )
