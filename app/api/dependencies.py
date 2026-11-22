"""Dependencies shared by the API's endpoints."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Connection

from app.repositories.users import SQLUserRepository, User, UserRepository


def get_connection(request: Request) -> Iterator[Connection]:
    """Provide the request's connection, in a savepoint for the endpoint's work.

    The current-user resolver opens the connection and its transaction. The
    savepoint rolls back if the endpoint raises, so a failed request keeps
    none of its writes even though the resolver's transaction commits.

    Args:
        request: The request, after the current-user resolver has run.

    Yields:
        The request's database connection.
    """
    connection: Connection = request.state.connection
    with connection.begin_nested():
        yield connection


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


def get_current_user(request: Request) -> User:
    """Provide the user the current-user resolver found for the request.

    Args:
        request: The request, after the current-user resolver has run.

    Returns:
        The current user.
    """
    user: User = request.state.user
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
