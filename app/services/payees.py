"""Business rules for payees."""

from uuid import UUID

from app.core.errors import NameConflictError, NotFoundError
from app.core.list_options import NameSort
from app.repositories.lists import LookupResourceCriteria, RecordPage
from app.repositories.payees import Payee, PayeeRepository


class PayeeNameConflictError(NameConflictError):
    """A name is already used by another of the user's payees, archived or not."""

    def __init__(self, existing: Payee) -> None:
        """Name the payee that already has the name.

        Args:
            existing: The payee with the name.
        """
        super().__init__(f"name used by payee {existing.id}")
        self.existing = existing


def create_payee(payee_repo: PayeeRepository, user_id: UUID, name: str) -> Payee:
    """Create an active payee for a user.

    Args:
        payee_repo: The repository to store the payee in.
        user_id: The id of the user who owns the payee.
        name: The payee's name.

    Returns:
        The new payee.

    Raises:
        PayeeNameConflictError: If the user has another payee with the name,
            ignoring case, archived or not.
    """
    try:
        return payee_repo.create(user_id, name)
    except NameConflictError as error:
        existing = payee_repo.get_by_name(user_id, name)
        # A clashing payee deleted since the insert can't be named, so the
        # conflict is reported as an unexpected error.
        if existing is None:
            raise
        raise PayeeNameConflictError(existing) from error


def get_payee(payee_repo: PayeeRepository, user_id: UUID, payee_id: UUID) -> Payee:
    """Find one of a user's payees, archived or not.

    Args:
        payee_repo: The repository to look the payee up in.
        user_id: The id of the user who owns the payee.
        payee_id: The id of the payee to find.

    Returns:
        The payee.

    Raises:
        NotFoundError: If the user has no payee with that id, which includes
            another user's payee.
    """
    payee = payee_repo.get(user_id, payee_id)
    if payee is None:
        raise NotFoundError
    return payee


def list_payees(
    payee_repo: PayeeRepository,
    user_id: UUID,
    criteria: LookupResourceCriteria[NameSort],
) -> RecordPage[Payee]:
    """List one page of a user's payees.

    Args:
        payee_repo: The repository to list the payees from.
        user_id: The id of the user who owns the payees.
        criteria: Which of the payees to list, and which page of them.

    Returns:
        The payees on the page, and how many match in all.
    """
    return payee_repo.list(user_id, criteria)
