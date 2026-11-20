"""Schemas for problem details (RFC 9457) error responses."""

from app.schemas.base import ApiModel


class ProblemErrorEntry(ApiModel):
    """One field-level problem, located by a body pointer or a parameter name."""

    detail: str
    pointer: str | None = None
    parameter: str | None = None


class Problem(ApiModel):
    """An error response, sent as ``application/problem+json``."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    errors: list[ProblemErrorEntry] | None = None
