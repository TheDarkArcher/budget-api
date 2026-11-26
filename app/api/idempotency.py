"""Create requests that can be repeated safely, by their ``Idempotency-Key``."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import Header, Response
from pydantic import StringConstraints, WithJsonSchema

from app.api.problems import IDEMPOTENCY_KEY_MISMATCH, ProblemError
from app.repositories.idempotency_keys import IdempotencyKeyRepository, StoredResponse
from app.schemas.base import ApiModel

MAX_KEY_LENGTH = 255
KEY_LIFETIME = timedelta(hours=24)
MISMATCH_DETAIL = "The Idempotency-Key was already used with a different request."

# A request without a key leaves the header out, so it isn't documented as
# nullable.
IdempotencyKeyHeader = Annotated[
    Annotated[str, StringConstraints(min_length=1, max_length=MAX_KEY_LENGTH)] | None,
    WithJsonSchema({"type": "string", "minLength": 1, "maxLength": MAX_KEY_LENGTH}),
    Header(
        alias="Idempotency-Key",
        description="Makes the request safe to repeat: a repeat with the same key"
        " and request returns the original response instead of creating another"
        " record, and the same key with a different request returns a 422"
        " `/problems/idempotency-key-mismatch`. A repeat sent while the first"
        " request is still running waits for it. Choose a unique key, such as a"
        " UUID, for each record to create. A key lasts 24 hours, and only"
        " successful creates are stored, so a failed request can be sent again"
        " with the same key. The key is the header's text as sent, including any"
        " quotes, and the header may be sent only once.",
    ),
]


@dataclass(frozen=True)
class NewRecord:
    """A record a request created.

    Attributes:
        record: The record, as the response sends it.
        location: The record's path, for the ``Location`` header.
    """

    record: ApiModel
    location: str


class IdempotentCreate:
    """A create request, carried out only once if it was sent with a key."""

    def __init__(
        self,
        key_repo: IdempotencyKeyRepository,
        user_id: UUID | None,
        method: str,
        path: str,
        key: str | None,
    ) -> None:
        """Describe the request.

        Args:
            key_repo: The repository to store the key in, sharing the create's
                unit of work, so the key is kept only if the record is.
            user_id: The id of the user the request acts as, or ``None``.
            method: The request's method.
            path: The request's path.
            key: The key the request was sent with, if any.
        """
        self._key_repo = key_repo
        self._user_id = user_id
        self._method = method
        self._path = path
        self._key = key

    def run(self, body: ApiModel, create: Callable[[], NewRecord]) -> Response:
        """Create the record, or replay the response to an earlier request.

        Call this from the endpoint rather than a dependency: dependencies run
        even when the body is invalid, which comes first in the error order.

        Args:
            body: The request's validated body.
            create: Creates the record.

        Returns:
            The 201 response, exactly as first sent if the request is a repeat.

        Raises:
            ProblemError: If the key was used with a different request.
        """
        if self._key is None:
            return send(storable_response(create()))

        request_hash = hash_request(self._method, self._path, body)
        self._key_repo.delete_older_than(KEY_LIFETIME)
        earlier = self._key_repo.claim(self._user_id, self._key, request_hash)

        if earlier is None:
            response = storable_response(create())
            self._key_repo.store_response(self._user_id, self._key, response)
            return send(response)

        if earlier.request_hash != request_hash:
            raise ProblemError(IDEMPOTENCY_KEY_MISMATCH, MISMATCH_DETAIL)
        return send(earlier.response)


def hash_request(method: str, path: str, body: ApiModel) -> str:
    """Hash what makes two requests the same.

    Fields left at their defaults aren't hashed, so a field added to a body
    later, with a default, doesn't change the hashes already stored.

    Args:
        method: The request's method.
        path: The request's path.
        body: The request's validated body.

    Returns:
        The hash, equal for requests that are the same.
    """
    fields = body.model_dump(mode="json", by_alias=True, exclude_defaults=True)
    request = json.dumps([method, path, fields], sort_keys=True)
    return hashlib.sha256(request.encode()).hexdigest()


def storable_response(new_record: NewRecord) -> StoredResponse:
    """Build the response for a new record, ready to store.

    Args:
        new_record: The new record.

    Returns:
        The 201 response.
    """
    return StoredResponse(
        status=HTTPStatus.CREATED,
        body=new_record.record.model_dump_json(by_alias=True),
        location=new_record.location,
    )


def send(response: StoredResponse) -> Response:
    """Build the HTTP response for a create.

    Args:
        response: The response, as stored.

    Returns:
        The response to send.
    """
    return Response(
        response.body,
        status_code=response.status,
        headers={"Location": response.location},
        media_type="application/json",
    )
