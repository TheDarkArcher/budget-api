"""Business rules for payees."""

from uuid import UUID

from app.core.errors import ArchivedError, NameConflictError, NotFoundError
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
        raise name_conflict(payee_repo, user_id, name, error) from error


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


def update_payee(
    payee_repo: PayeeRepository, user_id: UUID, payee_id: UUID, name: str
) -> Payee:
    """Update one of a user's payees entirely, which only renames it.

    Args:
        payee_repo: The repository the payee is stored in.
        user_id: The id of the user who owns the payee.
        payee_id: The id of the payee to update.
        name: The payee's new name.

    Returns:
        The updated payee.

    Raises:
        NotFoundError: If the user has no payee with that id, which includes
            another user's payee.
        ArchivedError: If the payee is archived, whatever the new name.
        PayeeNameConflictError: If the user has another payee with the name,
            ignoring case, archived or not.
    """
    if get_payee(payee_repo, user_id, payee_id).archived_at is not None:
        raise ArchivedError
    try:
        updated = payee_repo.update(user_id, payee_id, name)
    except NameConflictError as error:
        raise name_conflict(payee_repo, user_id, name, error) from error
    # A payee deleted since it was found is reported as not found.
    if updated is None:
        raise NotFoundError
    return updated


def archive_payee(payee_repo: PayeeRepository, user_id: UUID, payee_id: UUID) -> Payee:
    """Archive one of a user's payees, leaving an archived one unchanged.

    Args:
        payee_repo: The repository the payee is stored in.
        user_id: The id of the user who owns the payee.
        payee_id: The id of the payee to archive.

    Returns:
        The archived payee.

    Raises:
        NotFoundError: If the user has no payee with that id, which includes
            another user's payee.
    """
    archived = payee_repo.archive(user_id, payee_id)
    # The repository archives only an active payee, so any other is looked up.
    return archived or get_payee(payee_repo, user_id, payee_id)


def unarchive_payee(
    payee_repo: PayeeRepository, user_id: UUID, payee_id: UUID
) -> Payee:
    """Unarchive one of a user's payees, leaving an active one unchanged.

    Args:
        payee_repo: The repository the payee is stored in.
        user_id: The id of the user who owns the payee.
        payee_id: The id of the payee to unarchive.

    Returns:
        The active payee.

    Raises:
        NotFoundError: If the user has no payee with that id, which includes
            another user's payee.
    """
    unarchived = payee_repo.unarchive(user_id, payee_id)
    # The repository unarchives only an archived payee, so any other is looked up.
    return unarchived or get_payee(payee_repo, user_id, payee_id)


def name_conflict(
    payee_repo: PayeeRepository,
    user_id: UUID,
    name: str,
    error: NameConflictError,
) -> PayeeNameConflictError:
    """Name the payee a refused name belongs to.

    Args:
        payee_repo: The repository the payees are stored in.
        user_id: The id of the user who owns the payees.
        name: The name the repository refused.
        error: The repository's refusal.

    Returns:
        The conflict, naming the payee with the name.

    Raises:
        NameConflictError: The refusal itself, if no payee has the name, as
            one deleted since the refusal can't be named.
    """
    existing = payee_repo.get_by_name(user_id, name)
    if existing is None:
        raise error
    return PayeeNameConflictError(existing)
