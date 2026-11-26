"""The route class for versioned API endpoints."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.datastructures import Headers, QueryParams

# The headers the API's own rules allow only once, in lower case.
SINGLE_VALUE_HEADERS = frozenset({"idempotency-key"})


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


class SingleValueHeaders(Headers):
    """Headers of which some are refused when repeated."""

    def get(self, key: str, default: Any = None) -> Any:
        """Return a header's value.

        Args:
            key: The header's name.
            default: What to return if the header wasn't sent.

        Returns:
            The value, or a ``RepeatedParameter`` if the header may be sent
            only once and was sent more often.
        """
        if key.lower() in SINGLE_VALUE_HEADERS and len(self.getlist(key)) > 1:
            return RepeatedParameter()
        return super().get(key, default)


class SingleValueRequest(Request):
    """A request whose single-value parameters are refused when repeated."""

    @property
    def headers(self) -> Headers:
        """The request's headers."""
        if not hasattr(self, "_single_value_headers"):
            self._single_value_headers = SingleValueHeaders(scope=self.scope)
        return self._single_value_headers

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

    It refuses the headers in ``SINGLE_VALUE_HEADERS`` sent twice too. Every
    router of a versioned API sets this as its ``route_class``, as FastAPI
    otherwise keeps one of the values sent.
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
            """Handle a request, refusing repeated single-value parameters.

            Args:
                request: The incoming request.

            Returns:
                The endpoint's response.
            """
            return await handle(SingleValueRequest(request.scope, request.receive))

        return handle_single_values
