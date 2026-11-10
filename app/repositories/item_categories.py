"""SQL for the ``item_categories`` table."""

from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import Connection, text


class ItemCategoryRepository(ABC):
    """Interface for storing item categories."""

    @abstractmethod
    def create(self, user_id: UUID, name: str) -> UUID:
        """Create an item category.

        Args:
            user_id: The id of the user who owns the category.
            name: The category's name.

        Returns:
            The new category's id.
        """


class SQLItemCategoryRepository(ItemCategoryRepository):
    """SQL implementation of the item category repository."""

    def __init__(self, connection: Connection) -> None:
        """Create the repository.

        Args:
            connection: The connection every query runs on.
        """
        self._connection = connection

    def create(self, user_id: UUID, name: str) -> UUID:
        """Create an item category.

        Args:
            user_id: The id of the user who owns the category.
            name: The category's name.

        Returns:
            The new category's id.
        """
        category_id: UUID = self._connection.execute(
            text(
                "INSERT INTO item_categories (user_id, name)"
                " VALUES (:user_id, :name) RETURNING id"
            ),
            {"user_id": user_id, "name": name},
        ).scalar_one()
        return category_id
