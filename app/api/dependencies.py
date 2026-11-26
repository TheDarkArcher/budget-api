"""Dependencies shared by the API's endpoints."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Connection

from app.api.idempotency import IdempotencyKeyHeader, IdempotentCreate
from app.database.engine import ConnectionOpener
from app.repositories.idempotency_keys import SQLIdempotencyKeyRepository
from app.repositories.payees import PayeeRepository, SQLPayeeRepository
from app.repositories.users import SQLUserRepository, User, UserRepository


def get_connection(request: Request) -> Iterator[Connection]:
    """Provide the request's connection, in a transaction for the endpoint's work.

    The transaction commits when the endpoint returns, before the response
    starts, so a failed commit gives a 500 rather than a success. It rolls
    back if the endpoint raises, so a failed request keeps none of its writes.

    Args:
        request: The request being handled.

    Yields:
        The request's database connection.
    """
    open_connection: ConnectionOpener = request.app.state.open_connection
    with open_connection() as connection:
        yield connection


ConnectionDep = Annotated[Connection, Depends(get_connection, scope="function")]


def get_user_repository(connection: ConnectionDep) -> UserRepository:
    """Provide the user repository for one request.

    Args:
        connection: The request's database connection.

    Returns:
        A user repository on that connection.
    """
    return SQLUserRepository(connection)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_payee_repository(connection: ConnectionDep) -> PayeeRepository:
    """Provide the payee repository for one request.

    Args:
        connection: The request's database connection.

    Returns:
        A payee repository on that connection.
    """
    return SQLPayeeRepository(connection)


PayeeRepositoryDep = Annotated[PayeeRepository, Depends(get_payee_repository)]


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


def get_idempotent_create(
    request: Request,
    connection: ConnectionDep,
    user: CurrentUserDep,
    key: IdempotencyKeyHeader = None,
) -> IdempotentCreate:
    """Provide the current user's create request, with its key if it has one.

    Args:
        request: The request, after the current-user resolver has run.
        connection: The request's database connection.
        user: The current user.
        key: The request's ``Idempotency-Key`` header.

    Returns:
        The create request.
    """
    return IdempotentCreate(
        SQLIdempotencyKeyRepository(connection),
        user.id,
        request.method,
        request.scope["path"],
        key,
    )


IdempotentCreateDep = Annotated[IdempotentCreate, Depends(get_idempotent_create)]
