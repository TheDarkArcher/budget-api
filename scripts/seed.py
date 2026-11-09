"""Create the dummy user and their default data, unless they already exist.

Safe to run again: the dummy user has a fixed id, so a second run finds them
and changes nothing. The user and their defaults are created in one database
transaction, so a failed run leaves nothing behind. Database errors are
logged; any other error, such as invalid settings, ends with a traceback.
Either way the exit status is 1.
"""

import logging
import sys

from sqlalchemy import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.dummy_user import DUMMY_USER_ID, DUMMY_USER_NAME
from app.database.engine import get_engine
from app.repositories import users
from app.services.users import provision_user

logger = logging.getLogger(__name__)


def seed_dummy_user(connection: Connection) -> bool:
    """Create the dummy user and their defaults, unless the user exists.

    Args:
        connection: The connection to write on, inside a transaction.

    Returns:
        ``True`` if the dummy user was created, ``False`` if they already
        existed.
    """
    if not users.insert(connection, DUMMY_USER_ID, DUMMY_USER_NAME):
        return False
    provision_user(connection, DUMMY_USER_ID)
    return True


def main() -> int:
    """Seed the database in one transaction.

    Returns:
        The exit status: 0 if the dummy user exists afterwards, 1 if a
        database error made seeding fail and roll back.
    """
    try:
        with get_engine().begin() as connection:
            created = seed_dummy_user(connection)
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
