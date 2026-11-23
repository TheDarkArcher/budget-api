"""Schemas for problem details (RFC 9457) error responses."""

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from app.schemas.base import ApiModel


class ProblemErrorEntry(ApiModel):
    """One problem with a request, located by either `pointer` or `parameter`."""

    detail: str = Field(description="What is wrong, safe to show to the user.")
    # Left out rather than sent as null when unset, so not documented as nullable.
    pointer: str | SkipJsonSchema[None] = Field(
        default=None,
        description="A JSON Pointer (RFC 6901) into the request body, using its"
        " camelCase names, such as `/lines/1/itemSizeId`. Present when the"
        " problem is in the body.",
    )
    parameter: str | SkipJsonSchema[None] = Field(
        default=None,
        description="The name of the query or header parameter, as sent,"
        " such as `pageSize`. Present when the problem is in a parameter.",
    )


class Problem(ApiModel):
    """An error response, sent as `application/problem+json` (RFC 9457)."""

    type: str = Field(
        description="A problem type, used as an identifier: a path-absolute URI"
        " reference such as `/problems/name-conflict` for 409 and 422 responses,"
        " and `about:blank` for every other status. Clients should accept types"
        " they don't know.",
    )
    title: str = Field(
        description="A short, fixed summary of the problem type, or the HTTP"
        " status phrase for `about:blank`. For display only; match on `type`."
    )
    status: int = Field(description="The HTTP status code of the response.")
    detail: str = Field(
        description="What went wrong in this request, safe to show to the user."
    )
    errors: list[ProblemErrorEntry] | SkipJsonSchema[None] = Field(
        default=None,
        description="The problems with individual fields or parameters. Present"
        " only when the request had any.",
    )
