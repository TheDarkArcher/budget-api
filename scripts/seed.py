"""Create the dummy user and their default data, unless they already exist.

Safe to run again: the dummy user has a fixed id, so a second run finds them
and changes nothing. The user and their defaults are created in one database
transaction, so a failed run leaves nothing behind. Database errors are
logged; any other error, such as invalid settings, ends with a traceback.
Either way the exit status is 1.
"""

import logging
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.dummy_user import DUMMY_USER_ID, DUMMY_USER_NAME
from app.database.engine import get_engine
from app.repositories.item_categories import (
    ItemCategoryRepository,
    SQLItemCategoryRepository,
)
from app.repositories.transaction_categories import (
    SQLTransactionCategoryRepository,
    TransactionCategoryRepository,
)
from app.repositories.users import SQLUserRepository, UserRepository
from app.services.users import provision_user

logger = logging.getLogger(__name__)


def seed_dummy_user(
    user_repo: UserRepository,
    item_category_repo: ItemCategoryRepository,
    transaction_category_repo: TransactionCategoryRepository,
) -> bool:
    """Create the dummy user and their defaults, unless the user exists.

    Args:
        user_repo: The repository to create the dummy user with.
        item_category_repo: The repository to create the default item
            categories with.
        transaction_category_repo: The repository to create the default
            transaction categories and their item category links with.

    Returns:
        ``True`` if the dummy user was created, ``False`` if they already
        existed.
    """
    if not user_repo.create(DUMMY_USER_ID, DUMMY_USER_NAME):
        return False
    provision_user(item_category_repo, transaction_category_repo, DUMMY_USER_ID)
    return True


def main() -> int:
    """Seed the database in one transaction.

    Returns:
        The exit status: 0 if the dummy user exists afterwards, 1 if a
        database error made seeding fail and roll back.
    """
    try:
        with get_engine().begin() as connection:
            user_repo = SQLUserRepository(connection)
            item_category_repo = SQLItemCategoryRepository(connection)
            transaction_category_repo = SQLTransactionCategoryRepository(connection)
            created = seed_dummy_user(
                user_repo, item_category_repo, transaction_category_repo
            )
    except SQLAlchemyError:
        logger.exception("Seeding failed; nothing was changed")
        return 1
    if created:
        logger.info("Created the dummy user and their default categories")
    else:
        logger.info("The dummy user already exists; nothing to seed")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=get_settings().log_level, format="%(levelname)s %(message)s"
    )
    sys.exit(main())
