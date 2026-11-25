"""What a list can be sorted and filtered by."""

from enum import StrEnum


class SortOrder(StrEnum):
    """Which way a list is sorted."""

    ASC = "asc"
    DESC = "desc"


class NameSort(StrEnum):
    """What a list that only sorts by name can be sorted by."""

    NAME = "name"


class ArchivedFilter(StrEnum):
    """Which records a list holds: active, archived or both."""

    FALSE = "false"
    TRUE = "true"
    ALL = "all"
