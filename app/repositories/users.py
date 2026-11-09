"""SQL for the ``users`` table."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class User:
    """A user as stored in the database."""

    id: UUID
    name: str


class UserRepository(ABC):
    """Interface for storing users."""

    @abstractmethod
    def get(self, user_id: UUID) -> User | None:
        """Find a user by id.

        Args:
            user_id: The id of the user to find.

        Returns:
            The user, or ``None`` if no user has that id.
        """

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

    def get(self, user_id: UUID) -> User | None:
        """Find a user by id.

        Args:
            user_id: The id of the user to find.

        Returns:
            The user, or ``None`` if no user has that id.
        """
        row = self._connection.execute(
            text("SELECT id, name FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        return None if row is None else User(id=row.id, name=row.name)

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
