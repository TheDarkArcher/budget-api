"""Schemas for users."""

from uuid import UUID

from app.schemas.base import ApiModel


class UserResponse(ApiModel):
    """A user, as returned by the API."""

    id: UUID
    name: str
