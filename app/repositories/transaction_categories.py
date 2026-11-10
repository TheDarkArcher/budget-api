"""SQL for the ``transaction_categories`` table and its item category links."""

from abc import ABC, abstractmethod
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, text

type CategoryType = Literal["income", "expense"]


class TransactionCategoryRepository(ABC):
    """Interface for storing transaction categories and their item category links."""

    @abstractmethod
    def create(self, user_id: UUID, name: str, category_type: CategoryType) -> UUID:
        """Create a transaction category.

        Args:
            user_id: The id of the user who owns the category.
            name: The category's name.
            category_type: Whether the category is for income or expenses.

        Returns:
            The new category's id.
        """

    @abstractmethod
    def link_item_category(
        self, transaction_category_id: UUID, item_category_id: UUID
    ) -> None:
        """Link an item category to a transaction category.

        Args:
            transaction_category_id: The transaction category to link.
            item_category_id: The item category to link.
        """


class SQLTransactionCategoryRepository(TransactionCategoryRepository):
    """SQL implementation of the transaction category repository."""

    def __init__(self, connection: Connection) -> None:
        """Create the repository.

        Args:
            connection: The connection every query runs on.
        """
        self._connection = connection

    def create(self, user_id: UUID, name: str, category_type: CategoryType) -> UUID:
        """Create a transaction category.

        Args:
            user_id: The id of the user who owns the category.
            name: The category's name.
            category_type: Whether the category is for income or expenses.

        Returns:
            The new category's id.
        """
        category_id: UUID = self._connection.execute(
            text(
                "INSERT INTO transaction_categories (user_id, name, type)"
                " VALUES (:user_id, :name, :type) RETURNING id"
            ),
            {"user_id": user_id, "name": name, "type": category_type},
        ).scalar_one()
        return category_id

    def link_item_category(
        self, transaction_category_id: UUID, item_category_id: UUID
    ) -> None:
        """Link an item category to a transaction category.

        Args:
            transaction_category_id: The transaction category to link.
            item_category_id: The item category to link.
        """
        self._connection.execute(
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
