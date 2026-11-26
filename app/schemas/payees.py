"""Schemas for payees."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field

from app.repositories.payees import Payee
from app.schemas.base import ApiModel
from app.schemas.fields import Name


class PayeeRequest(ApiModel):
    """A payee, as a request to create or replace one sends it."""

    name: Name = Field(
        description="The payee's name. Surrounding whitespace is trimmed, and it"
        " must then be 1 to 100 characters long, with no NUL character."
    )


class PayeeResponse(ApiModel):
    """A payee, as the API returns it."""

    id: UUID = Field(description="The payee's id.")
    name: str = Field(description="The payee's name.")
    archived_at: datetime | None = Field(
        description="When the payee was archived, or null while it's active."
    )

    @classmethod
    def from_payee(cls, payee: Payee) -> Self:
        """Build the response for a stored payee.

        Args:
            payee: The payee.

        Returns:
            The payee as the API returns it.
        """
        return cls(id=payee.id, name=payee.name, archived_at=payee.archived_at)
