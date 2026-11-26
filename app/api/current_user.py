"""The current-user resolver, in front of every versioned API request."""

import logging
import re
from http import HTTPStatus

from sqlalchemy import Connection
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.problems import ABOUT_BLANK, problem_response
from app.core.dummy_user import DUMMY_USER_ID
from app.database.engine import ConnectionOpener
from app.repositories.users import SQLUserRepository, User
from app.schemas.problems import Problem
from app.services.users import get_user

logger = logging.getLogger(__name__)

# /api/v1, /api/v2 and so on; unversioned paths need no current user.
VERSIONED_API_PATH = re.compile(r"/api/v\d+(/|$)")


def find_current_user(connection: Connection) -> User | None:
    """Find the user a request acts as.

    Every request acts as the dummy user until real authentication exists.
    This is the only place that decides who the current user is, so adding
    authentication only means replacing this function.

    Args:
        connection: The connection to look the user up on.

    Returns:
        The current user, or None if there isn't one, e.g. because the
        database hasn't been seeded.
    """
    return get_user(SQLUserRepository(connection), DUMMY_USER_ID)


class CurrentUserMiddleware:
    """Resolve the current user in front of every versioned API request.

    The middleware looks the user up on a connection of its own, opened with
    the opener it's given and closed before the request goes on, and answers
    403 before the request is routed or parsed when there is no current
    user. Otherwise it leaves the user on the request's state for the
    endpoint.
    """

    def __init__(self, app: ASGIApp, open_connection: ConnectionOpener) -> None:
        """Wrap the rest of the application.

        Args:
            app: The ASGI application the middleware runs in front of.
            open_connection: Opens the connection the user is looked up on.
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
        user = await run_in_threadpool(self.look_up_user)
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
            return
        # A copy, so the user doesn't leak to the layers in front of the
        # resolver, as the ASGI spec advises.
        state = {**scope.get("state", {}), "user": user}
        await self.app({**scope, "state": state}, receive, send)

    def look_up_user(self) -> User | None:
        """Find the current user on a connection that closes straight after.

        Returns:
            The current user, or None if there isn't one.
        """
        with self.open_connection() as connection:
            return find_current_user(connection)


def route_path(scope: Scope) -> str:
    """Give a request's path without the root path a proxy mounts the app at.

    Args:
        scope: The request's ASGI scope, whose path includes the root path.

    Returns:
        The path the app's routes match against.
    """
    path: str = scope["path"]
    return path.removeprefix(scope.get("root_path", ""))
