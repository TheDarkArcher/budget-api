"""Dependencies shared by the API's endpoints."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import Connection

from app.core.dummy_user import DUMMY_USER_ID
from app.database.engine import get_connection
from app.repositories.users import SQLUserRepository, User, UserRepository
from app.services.users import get_user

logger = logging.getLogger(__name__)

ConnectionDep = Annotated[Connection, Depends(get_connection)]


def get_user_repository(connection: ConnectionDep) -> UserRepository:
    """Provide the user repository for one request.

    Args:
        connection: The request's database connection.

    Returns:
        A user repository on that connection.
    """
    return SQLUserRepository(connection)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_current_user(user_repo: UserRepositoryDep) -> User:
    """Resolve the user the request acts as.

    Every request acts as the dummy user until real authentication exists.
    This is the only place that decides who the current user is, so adding
    authentication only means replacing this function.

    Args:
        user_repo: The repository to look the current user up in.

    Returns:
        The current user.

    Raises:
        HTTPException: 403 if the user doesn't exist, e.g. because the
            database hasn't been seeded.
    """
    user = get_user(user_repo, DUMMY_USER_ID)
    if user is None:
        logger.warning("The dummy user doesn't exist; has the database been seeded?")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorised")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
