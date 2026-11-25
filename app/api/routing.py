"""The route class for versioned API endpoints."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.datastructures import QueryParams


class RepeatedParameter:
    """Stands in for the value of a parameter sent more than once.

    No parameter's type accepts it, so it fails request validation.
    """


class SingleValueQueryParams(QueryParams):
    """Query parameters whose single values are refused when repeated.

    FastAPI reads a parameter declared as a list with ``getlist``, so only
    those can be sent more than once.
    """

    def get(self, key: Any, default: Any = None) -> Any:
        """Return a parameter's only value.

        Args:
            key: The parameter's name.
            default: What to return if the parameter wasn't sent.

        Returns:
            The value, or a ``RepeatedParameter`` if the parameter was sent
            more than once.
        """
        if len(self.getlist(key)) > 1:
            return RepeatedParameter()
        return super().get(key, default)


class SingleValueRequest(Request):
    """A request whose query parameters are refused when repeated."""

    @property
    def query_params(self) -> QueryParams:
        """The request's query parameters."""
        if not hasattr(self, "_single_value_query_params"):
            self._single_value_query_params = SingleValueQueryParams(
                self.scope["query_string"]
            )
        return self._single_value_query_params


class SingleValueRoute(APIRoute):
    """A route that refuses a query parameter sent twice, unless it's a list.

    Every router of a versioned API sets this as its ``route_class``, as
    FastAPI otherwise keeps the last value sent.
    """

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Build the route's handler.

        Returns:
            FastAPI's own handler, given a request that refuses repeats.
        """
        handle = super().get_route_handler()

        async def handle_single_values(request: Request) -> Response:
            """Handle a request, refusing repeated query parameters.

            Args:
                request: The incoming request.

            Returns:
                The endpoint's response.
            """
            return await handle(SingleValueRequest(request.scope, request.receive))

        return handle_single_values
