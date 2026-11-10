"""SQL for the ``users`` table."""

from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import Connection, text


class UserRepository(ABC):
    """Interface for storing users."""

    @abstractmethod
    def create(self, user_id: UUID, name: str) -> bool:
        """Create a user with the given id, unless one already exists.

        Args:
            user_id: The new user's id.
            name: The new user's name.

        Returns:
            ``True`` if the user was inserted, ``False`` if a user with that id
            already existed.
        """


class SQLUserRepository(UserRepository):
    """SQL implementation of the user repository."""

    def __init__(self, connection: Connection) -> None:
        """Create the repository.

        Args:
            connection: The connection every query runs on.
        """
        self._connection = connection

    def create(self, user_id: UUID, name: str) -> bool:
        """Create a user with the given id, unless one already exists.

        Args:
            user_id: The new user's id.
            name: The new user's name.

        Returns:
            ``True`` if the user was inserted, ``False`` if a user with that id
            already existed.
        """
        inserted = self._connection.execute(
            text(
                "INSERT INTO users (id, name) VALUES (:id, :name)"
                " ON CONFLICT (id) DO NOTHING RETURNING id"
            ),
            {"id": user_id, "name": name},
        ).first()
        return inserted is not None
