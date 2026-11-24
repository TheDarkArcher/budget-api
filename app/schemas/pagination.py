"""Schemas for paged lists."""

from pydantic import Field

from app.schemas.base import ApiModel


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
