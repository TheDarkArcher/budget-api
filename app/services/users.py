"""Business rules for users."""

from uuid import UUID

from app.repositories.item_categories import ItemCategoryRepository
from app.repositories.transaction_categories import (
    CategoryType,
    TransactionCategoryRepository,
)

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


def provision_user(
    item_category_repo: ItemCategoryRepository,
    transaction_category_repo: TransactionCategoryRepository,
    user_id: UUID,
) -> None:
    """Create a new user's default categories and the links between them.

    Writes through the given repositories, so it is part of the database
    transaction they share: if anything fails, none of the defaults are kept.

    Args:
        item_category_repo: The repository to create the item categories with.
        transaction_category_repo: The repository to create the transaction
            categories and their item category links with.
        user_id: The id of the user to provision, who must already exist.
    """
    item_category_ids = {
        name: item_category_repo.create(user_id, name)
        for name in DEFAULT_ITEM_CATEGORIES
    }
    for name, category_type in DEFAULT_TRANSACTION_CATEGORIES.items():
        transaction_category_id = transaction_category_repo.create(
            user_id, name, category_type
        )
        for item_category in DEFAULT_CATEGORY_LINKS[name]:
            transaction_category_repo.link_item_category(
                transaction_category_id, item_category_ids[item_category]
            )
