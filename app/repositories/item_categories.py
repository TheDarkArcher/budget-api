"""SQL for the ``item_categories`` table."""

from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import Connection, tstring

from app.repositories.sql_errors import translate_sql_constraint_errors


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

        Raises:
            NameConflictError: If the user has another category with the name.
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

        Raises:
            NameConflictError: If the user has another category with the name.
        """
        with translate_sql_constraint_errors(self._connection):
            category_id: UUID = self._connection.execute(
                tstring(t"""
                    INSERT INTO item_categories (user_id, name)
                    VALUES ({user_id}, {name})
                    RETURNING id
                """)
            ).scalar_one()
        return category_id
