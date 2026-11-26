"""Business rules for payees."""

from uuid import UUID

from app.core.errors import NotFoundError
from app.repositories.payees import Payee, PayeeRepository


def create_payee(payee_repo: PayeeRepository, user_id: UUID, name: str) -> Payee:
    """Create an active payee for a user.

    Args:
        payee_repo: The repository to store the payee in.
        user_id: The id of the user who owns the payee.
        name: The payee's name.

    Returns:
        The new payee.
    """
    return payee_repo.create(user_id, name)


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
