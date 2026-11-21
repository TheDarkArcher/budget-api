"""Domain errors: rules a request broke, raised below the API and reported by it."""

from enum import StrEnum


class DomainError(Exception):
    """A request broke a domain rule, so it can't be carried out."""


class NameConflictError(DomainError):
    """A name is already used by another of the user's records, archived or not."""


class Blocker(StrEnum):
    """What keeps a record in use, so it can't be deleted."""

    TRANSACTION = "transaction"
    ITEM = "item"
    ITEM_CATEGORY = "item-category"


class InUseError(DomainError):
    """A record can't be deleted because something still uses it."""

    def __init__(self, blocked_by: Blocker) -> None:
        """Name what keeps the record in use.

        Args:
            blocked_by: What uses the record.
        """
        super().__init__(f"in use by {blocked_by}")
        self.blocked_by = blocked_by


class ArchivedError(DomainError):
    """An archived record, or a link to an archived category, can't be changed."""


class TypeChangeError(DomainError):
    """A transaction category's type can't be changed after it's created."""
