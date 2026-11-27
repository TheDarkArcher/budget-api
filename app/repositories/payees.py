"""SQL for the ``payees`` table."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, Row, tstring

from app.core.list_options import NameSort
from app.repositories.lists import LookupResourceCriteria, RecordPage
from app.repositories.sql_errors import translate_sql_constraint_errors
from app.repositories.sql_lists import SQL_NAME_SORTS, SQLLookupResourceLists


@dataclass(frozen=True)
class Payee:
    """A payee as stored.

    Attributes:
        id: The payee's id.
        name: The payee's name.
        archived_at: When the payee was archived, or ``None`` while it's active.
    """

    id: UUID
    name: str
    archived_at: datetime | None


class PayeeRepository(ABC):
    """Interface for storing payees.

    Every method is scoped to one user, whose payees are the only ones it
    sees.
    """

    @abstractmethod
    def create(self, user_id: UUID, name: str) -> Payee:
        """Create an active payee.

        Args:
            user_id: The id of the user who owns the payee.
            name: The payee's name.

        Returns:
            The new payee.

        Raises:
            NameConflictError: If the user has another payee with the name.
        """

    @abstractmethod
    def get(self, user_id: UUID, payee_id: UUID) -> Payee | None:
        """Find one of a user's payees, archived or not.

        Args:
            user_id: The id of the user who owns the payee.
            payee_id: The id of the payee to find.

        Returns:
            The payee, or ``None`` if the user has no payee with that id.
        """

    @abstractmethod
    def list(
        self, user_id: UUID, criteria: LookupResourceCriteria[NameSort]
    ) -> RecordPage[Payee]:
        """List one page of a user's payees.

        Args:
            user_id: The id of the user who owns the payees.
            criteria: Which of the payees to list, and which page of them.

        Returns:
            The payees on the page, and how many match in all.
        """

    @abstractmethod
    def get_by_name(self, user_id: UUID, name: str) -> Payee | None:
        """Find the user's payee with a name, ignoring case, archived or not.

        Args:
            user_id: The id of the user who owns the payee.
            name: The name to look for.

        Returns:
            The payee, or ``None`` if the user has no payee with that name.
        """


class SQLPayeeRepository(PayeeRepository):
    """SQL implementation of the payee repository."""

    def __init__(self, connection: Connection) -> None:
        """Create the repository.

        Args:
            connection: The connection every query runs on.
        """
        self._connection = connection

    def create(self, user_id: UUID, name: str) -> Payee:
        """Create an active payee.

        Args:
            user_id: The id of the user who owns the payee.
            name: The payee's name.

        Returns:
            The new payee.

        Raises:
            NameConflictError: If the user has another payee with the name.
        """
        with translate_sql_constraint_errors(self._connection):
            row = self._connection.execute(
                tstring(t"""
                    INSERT INTO payees (user_id, name)
                    VALUES ({user_id}, {name})
                    RETURNING id, name, archived_at
                """)
            ).one()
        return self._payee(row)

    def get(self, user_id: UUID, payee_id: UUID) -> Payee | None:
        """Find one of a user's payees, archived or not.

        Args:
            user_id: The id of the user who owns the payee.
            payee_id: The id of the payee to find.

        Returns:
            The payee, or ``None`` if the user has no payee with that id.
        """
        row = self._connection.execute(
            tstring(t"""
                SELECT id, name, archived_at
                FROM payees
                WHERE user_id = {user_id} AND id = {payee_id}
            """)
        ).first()
        return None if row is None else self._payee(row)

    def get_by_name(self, user_id: UUID, name: str) -> Payee | None:
        """Find the user's payee with a name, ignoring case, archived or not.

        Args:
            user_id: The id of the user who owns the payee.
            name: The name to look for.

        Returns:
            The payee, or ``None`` if the user has no payee with that name.
        """
        row = self._connection.execute(
            tstring(t"""
                SELECT id, name, archived_at
                FROM payees
                WHERE user_id = {user_id} AND lower(name) = lower({name})
            """)
        ).first()
        return None if row is None else self._payee(row)

    def list(
        self, user_id: UUID, criteria: LookupResourceCriteria[NameSort]
    ) -> RecordPage[Payee]:
        """List one page of a user's payees.

        Args:
            user_id: The id of the user who owns the payees.
            criteria: Which of the payees to list, and which page of them.

        Returns:
            The payees on the page, and how many match in all.
        """
        payees = tstring(t"""
            SELECT id, name, archived_at
            FROM payees
            WHERE user_id = {user_id}
        """)
        page = SQLLookupResourceLists(self._connection, SQL_NAME_SORTS).fetch_page(
            payees, criteria
        )
        return RecordPage([self._payee(row) for row in page.records], page.total_items)

    def _payee(self, row: Row[tuple[UUID, str, datetime | None]]) -> Payee:
        """Build a payee from a row of the ``payees`` table.

        Args:
            row: A row holding the payee's ``id``, ``name`` and ``archived_at``.

        Returns:
            The payee.
        """
        return Payee(id=row.id, name=row.name, archived_at=row.archived_at)
