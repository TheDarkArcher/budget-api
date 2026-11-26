"""SQL for the ``idempotency_keys`` table."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import Connection, tstring


@dataclass(frozen=True)
class StoredResponse:
    """The response a create request received, to send again to a repeat."""

    status: int
    body: str
    location: str


@dataclass(frozen=True)
class StoredRequest:
    """A create request that succeeded, with the response it received."""

    request_hash: str
    response: StoredResponse


class IdempotencyKeyRepository(ABC):
    """Interface for storing the create requests sent with an idempotency key.

    Keys are kept apart by the user who sent them. Requests with no user share
    keys among themselves.
    """

    # Deleting old keys through the repository suits a small, early system. At
    # scale, a store with a TTL or a scheduled job outside the app should
    # remove them, and this method would go.
    @abstractmethod
    def delete_older_than(self, age: timedelta) -> None:
        """Delete every user's keys that were claimed too long ago.

        Args:
            age: How old a key can be before it's deleted.
        """

    @abstractmethod
    def claim(
        self, user_id: UUID | None, key: str, request_hash: str
    ) -> StoredRequest | None:
        """Claim a key for a request, unless another request already used it.

        Waits for any unfinished request that has claimed the key, and claims
        it only if that request fails. A claim lasts only if the claiming
        request's unit of work succeeds.

        Args:
            user_id: The id of the user who sent the key, or ``None``.
            key: The key to claim.
            request_hash: What identifies the request the key was sent with.

        Returns:
            ``None`` if the key is now claimed, otherwise the request that
            used it.
        """

    @abstractmethod
    def store_response(
        self, user_id: UUID | None, key: str, response: StoredResponse
    ) -> None:
        """Store the response to the request that claimed a key.

        Args:
            user_id: The id of the user who sent the key, or ``None``.
            key: The claimed key.
            response: The response to store.
        """


class SQLIdempotencyKeyRepository(IdempotencyKeyRepository):
    """SQL implementation of the idempotency key repository."""

    def __init__(self, connection: Connection) -> None:
        """Create the repository.

        Args:
            connection: The connection every query runs on.
        """
        self._connection = connection

    def delete_older_than(self, age: timedelta) -> None:
        """Delete every user's keys that were claimed too long ago.

        Args:
            age: How old a key can be before it's deleted.
        """
        # Locking in id order stops concurrent deletes from deadlocking.
        self._connection.execute(
            tstring(t"""
                DELETE FROM idempotency_keys
                WHERE id IN (
                    SELECT id FROM idempotency_keys
                    WHERE created_at < now() - {age}
                    ORDER BY id
                    FOR UPDATE
                )
            """)
        )

    def claim(
        self, user_id: UUID | None, key: str, request_hash: str
    ) -> StoredRequest | None:
        """Claim a key for a request, unless another request already used it.

        Waits for any unfinished request that has claimed the key, and claims
        it only if that request fails. A claim lasts only if the claiming
        request's unit of work succeeds.

        Args:
            user_id: The id of the user who sent the key, or ``None``.
            key: The key to claim.
            request_hash: What identifies the request the key was sent with.

        Returns:
            ``None`` if the key is now claimed, otherwise the request that
            used it.
        """
        # Waits on the unique constraint while another transaction holds the key.
        claimed = self._connection.execute(
            tstring(t"""
                INSERT INTO idempotency_keys (user_id, key, request_hash)
                VALUES ({user_id}, {key}, {request_hash})
                ON CONFLICT (user_id, key) DO NOTHING
                RETURNING id
            """)
        ).first()
        if claimed is not None:
            return None

        # Under READ COMMITTED, a new statement sees a response that was
        # committed while the insert waited.
        row = self._connection.execute(
            tstring(t"""
                SELECT request_hash, response_status, response_body, response_location
                FROM idempotency_keys
                WHERE user_id IS NOT DISTINCT FROM {user_id} AND key = {key}
            """)
        ).first()

        # A key that expired and was deleted since the insert can be claimed
        # after all.
        if row is None:
            return self.claim(user_id, key, request_hash)
        return StoredRequest(
            request_hash=row.request_hash,
            response=StoredResponse(
                status=row.response_status,
                body=row.response_body,
                location=row.response_location,
            ),
        )

    def store_response(
        self, user_id: UUID | None, key: str, response: StoredResponse
    ) -> None:
        """Store the response to the request that claimed a key.

        Args:
            user_id: The id of the user who sent the key, or ``None``.
            key: The claimed key.
            response: The response to store.
        """
        self._connection.execute(
            tstring(t"""
                UPDATE idempotency_keys
                SET response_status = {response.status},
                    response_body = {response.body},
                    response_location = {response.location}
                WHERE user_id IS NOT DISTINCT FROM {user_id} AND key = {key}
            """)
        )
