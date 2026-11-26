"""Schemas for paged lists and their query parameters."""

import math
from enum import StrEnum
from typing import Annotated, Self, cast

from pydantic import AfterValidator, ConfigDict, Field, StringConstraints

from app.core.list_options import ArchivedFilter, NameSort, SortOrder
from app.schemas.base import ApiModel
from app.schemas.fields import reject_nul


class PageParameters(ApiModel):
    """The query parameters of every paged list."""

    # Only the camelCase names are sent, so `page_size` isn't a parameter.
    model_config = ConfigDict(populate_by_name=False)

    page: int = Field(default=1, ge=1, description="The page number, starting at 1.")
    page_size: int = Field(
        default=25, ge=1, le=200, description="The most records a page can hold."
    )


# `Sort` is the enum of the resource's allowed sorts. A resource that allows more
# than `name` gives its own enum in place of `NameSort`. One of its members must
# have the value `name`, the default, or every request without a `sort` is
# rejected.
class LookupResourceParameters[Sort: StrEnum = NameSort](PageParameters):
    """The query parameters of a lookup resource's list."""

    q: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=100),
        AfterValidator(reject_nul),
    ] = Field(
        default="",
        description="Lists only records whose name contains this text, ignoring"
        " case. Surrounding whitespace is trimmed, and blank text is ignored."
        " At most 100 characters after trimming, and no NUL character.",
    )
    # Validating the default turns it into the resource's own enum.
    sort: Sort = Field(
        default=cast(Sort, "name"),
        validate_default=True,
        description="What to sort the list by.",
    )
    order: SortOrder = Field(
        default=SortOrder.ASC,
        description="The direction to sort in. Records that sort equally are"
        " ordered by id, in the same direction.",
    )


class ArchivableLookupResourceParameters[Sort: StrEnum = NameSort](
    LookupResourceParameters[Sort]
):
    """The query parameters of a lookup resource whose records can be archived."""

    archived: ArchivedFilter = Field(
        default=ArchivedFilter.FALSE,
        description="Whether to list active records (`false`), archived records"
        " (`true`) or both (`all`).",
    )


# Subclass this per resource, such as `class PayeePage(Page[Payee])`, so the
# OpenAPI schema is named `PayeePage` rather than Pydantic's `Page_Payee_`.
class Page[T](ApiModel):
    """One page of a list of records."""

    data: list[T] = Field(description="The records on this page.")
    page: int = Field(description="The page number, starting at 1.")
    page_size: int = Field(description="The most records a page can hold.")
    total_items: int = Field(description="The number of records across all pages.")
    total_pages: int = Field(
        description="The number of pages, or 0 when there are no records."
    )

    @classmethod
    def build(cls, data: list[T], parameters: PageParameters, total_items: int) -> Self:
        """Build the page a request asked for.

        Args:
            data: The records on the page.
            parameters: The query parameters that chose the page.
            total_items: The number of records across all pages.

        Returns:
            The page, with the number of pages worked out.
        """
        return cls(
            data=data,
            page=parameters.page,
            page_size=parameters.page_size,
            total_items=total_items,
            total_pages=math.ceil(total_items / parameters.page_size),
        )
