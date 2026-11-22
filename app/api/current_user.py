"""The current-user resolver, in front of every versioned API request."""

import logging
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from http import HTTPStatus

from sqlalchemy import Connection
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.problems import ABOUT_BLANK, problem_response
from app.core.dummy_user import DUMMY_USER_ID
from app.repositories.users import SQLUserRepository, User
from app.schemas.problems import Problem
from app.services.users import get_user

logger = logging.getLogger(__name__)

# /api/v1, /api/v2 and so on; unversioned paths need no current user.
VERSIONED_API_PATH = re.compile(r"/api/v\d+(/|$)")

ConnectionOpener = Callable[[], AbstractContextManager[Connection]]


def find_current_user(connection: Connection) -> User | None:
    """Find the user a request acts as.

    Every request acts as the dummy user until real authentication exists.
    This is the only place that decides who the current user is, so adding
    authentication only means replacing this function.

    Args:
        connection: The request's database connection.

    Returns:
        The current user, or None if there isn't one, e.g. because the
        database hasn't been seeded.
    """
    return get_user(SQLUserRepository(connection), DUMMY_USER_ID)


class CurrentUserMiddleware:
    """Resolve the current user in front of every versioned API request.

    The middleware opens the request's connection and transaction with the
    opener it's given, and answers 403 before the request is routed or
    parsed when there is no current user. Otherwise it leaves the connection
    and the user on the request's state for the endpoint, and ends the
    transaction once the whole response is sent, after the endpoint's
    dependencies have closed.
    """

    def __init__(self, app: ASGIApp, open_connection: ConnectionOpener) -> None:
        """Wrap the rest of the application.

        Args:
            app: The ASGI application the middleware runs in front of.
            open_connection: Opens a request's connection and transaction.
        """
        self.app = app
        self.open_connection = open_connection

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection.

        Args:
            scope: The connection's ASGI scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] != "http" or not VERSIONED_API_PATH.match(route_path(scope)):
            await self.app(scope, receive, send)
            return
        db_transaction = self.open_connection()
        entered = False

        def enter() -> Connection:
            nonlocal entered
            connection = db_transaction.__enter__()
            entered = True
            return connection

        try:
            # Inside the try, so a disconnect that cancels the request as the
            # database transaction opens still closes it.
            connection = await run_in_threadpool(enter)
            user = await run_in_threadpool(find_current_user, connection)
            if user is None:
                logger.warning(
                    "The dummy user doesn't exist; has the database been seeded?"
                )
                forbidden = HTTPStatus.FORBIDDEN
                problem = Problem(
                    type=ABOUT_BLANK,
                    title=forbidden.phrase,
                    status=forbidden,
                    detail="Not authorised",
                )
                await problem_response(problem)(scope, receive, send)
            else:
                # A copy, so the connection and user don't leak to the
                # layers in front of the resolver, as the ASGI spec advises.
                state = {
                    **scope.get("state", {}),
                    "connection": connection,
                    "user": user,
                }
                await self.app({**scope, "state": state}, receive, send)
        except BaseException as error:
            # Hand the error to the database transaction so it rolls back,
            # then let it propagate as it would through a with block.
            if entered:
                await roll_back(db_transaction, error)
            raise
        await run_in_threadpool(db_transaction.__exit__, None, None, None)


def route_path(scope: Scope) -> str:
    """Give a request's path without the root path a proxy mounts the app at.

    Args:
        scope: The request's ASGI scope, whose path includes the root path.

    Returns:
        The path the app's routes match against.
    """
    path: str = scope["path"]
    return path.removeprefix(scope.get("root_path", ""))


async def roll_back(
    db_transaction: AbstractContextManager[Connection], error: BaseException
) -> None:
    """Roll back a request's database transaction after an error.

    A failure to roll back, such as on a dropped connection, is logged rather
    than raised, so the request's own error is the one that propagates.

    Args:
        db_transaction: The request's connection and database transaction.
        error: The error the request ended with.
    """
    try:
        await run_in_threadpool(
            db_transaction.__exit__, type(error), error, error.__traceback__
        )
    except Exception:
        logger.exception("Rolling back the request's database transaction failed")
