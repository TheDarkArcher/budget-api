"""What a repository's list takes and returns, whatever it stores records in."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.core.list_options import ArchivedFilter, SortOrder


@dataclass(frozen=True, kw_only=True)
class PageCriteria:
    """Which page of a list to fetch. A page past the end is empty.

    Attributes:
        page: The page number, starting at 1.
        page_size: The most records a page can hold.
    """

    page: int
    page_size: int


@dataclass(frozen=True, kw_only=True)
class LookupResourceCriteria[Sort: StrEnum](PageCriteria):
    """Which of a lookup resource's records to list, and which page of them.

    Every repository sorts text ignoring case and breaks ties by id.

    Attributes:
        q: Text the name must contain, ignoring case, with every character
            matched literally. Empty matches every name.
        archived: Whether to list active records, archived ones or both.
            ``ALL`` for records that are never archived.
        sort: What to sort by, from the resource's own sorts.
        order: The direction of every sort key, including the id.
    """

    q: str
    archived: ArchivedFilter
    sort: Sort
    order: SortOrder


@dataclass(frozen=True)
class RecordPage[T]:
    """One page of the records that match a list's criteria.

    Attributes:
        records: The records on the page, in order.
        total_items: The number of records across all pages.
    """

    records: Sequence[T]
    total_items: int
