"""Field types and the reference base shared by the API's schemas."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
)
from pydantic_core import PydanticCustomError

from app.schemas.base import ApiModel

# ASCII digits only, as `\d` would also match other scripts' digits.
DECIMAL_STRING_PATTERN = r"^[0-9]+(\.[0-9]+)?$"


def reject_nul(value: str) -> str:
    """Check a string holds no NUL character, which PostgreSQL can't store.

    Args:
        value: The string sent in the request.

    Returns:
        The string, unchanged.

    Raises:
        PydanticCustomError: If the string holds a NUL character.
    """
    if "\0" in value:
        raise PydanticCustomError(
            "nul_character", "String should not contain a NUL character"
        )
    return value


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(reject_nul),
]


def parse_decimal_string(value: Any) -> str | Decimal:
    """Check a request's decimal is a plain decimal string and trim it.

    A `Decimal` from Python code, such as a stored value, is passed through.

    Args:
        value: The value sent in the request, or a `Decimal`.

    Returns:
        The trimmed string, for Pydantic to parse as a `Decimal`, or the
        `Decimal` unchanged.

    Raises:
        PydanticCustomError: If the value isn't a `Decimal` or a string of
            digits with an optional decimal point and a digit on each side.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if re.fullmatch(DECIMAL_STRING_PATTERN, trimmed):
            return trimmed
    raise PydanticCustomError(
        "decimal_string",
        'Input should be a decimal number as a string, such as "3.5"',
    )


def format_decimal(value: Decimal) -> str:
    """Format a decimal for a response, without trailing zeros.

    Args:
        value: The decimal to format.

    Returns:
        The decimal in fixed-point notation, such as `"500"` or `"1.35"`.
    """
    return f"{value.normalize():f}"


# Limits, such as a size value's, are set with `Field` where the type is used.
DecimalString = Annotated[
    Decimal,
    BeforeValidator(parse_decimal_string),
    PlainSerializer(format_decimal, return_type=str, when_used="json"),
    WithJsonSchema(
        {"type": "string", "format": "decimal", "pattern": DECIMAL_STRING_PATTERN}
    ),
]


# Subclass this per resource, such as `PayeeReference`, so each reference has
# its own OpenAPI schema.
class Reference(ApiModel):
    """A related record, nested in another record."""

    id: UUID = Field(description="The record's id.")
    name: Name = Field(description="The record's name.")
    archived_at: datetime | None = Field(
        description="When the record was archived, or null while it's active."
    )
