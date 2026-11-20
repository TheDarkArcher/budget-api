"""Problem details (RFC 9457) responses for the API's errors."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic.alias_generators import to_camel
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint

from app.schemas.base import ApiModel
from app.schemas.problems import Problem, ProblemErrorEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProblemType:
    """A named problem type, used where a status has more than one meaning."""

    uri: str
    status: HTTPStatus
    title: str


NAME_CONFLICT = ProblemType(
    "/problems/name-conflict", HTTPStatus.CONFLICT, "Name already in use"
)
ARCHIVED = ProblemType("/problems/archived", HTTPStatus.CONFLICT, "Record archived")
PARENT_ARCHIVED_ITEM_CATEGORY = ProblemType(
    "/problems/parent-archived/item-category",
    HTTPStatus.CONFLICT,
    "Item category archived",
)
IN_USE_TRANSACTION = ProblemType(
    "/problems/in-use/transaction", HTTPStatus.CONFLICT, "In use by a transaction"
)
IN_USE_ITEM_CATEGORY = ProblemType(
    "/problems/in-use/item-category",
    HTTPStatus.CONFLICT,
    "Linked to an active item category",
)
IN_USE_ITEM = ProblemType(
    "/problems/in-use/item", HTTPStatus.CONFLICT, "In use by an item"
)
VALIDATION = ProblemType(
    "/problems/validation", HTTPStatus.UNPROCESSABLE_CONTENT, "Validation failed"
)
INVALID_REFERENCE = ProblemType(
    "/problems/invalid-reference", HTTPStatus.UNPROCESSABLE_CONTENT, "Invalid reference"
)
IDEMPOTENCY_KEY_MISMATCH = ProblemType(
    "/problems/idempotency-key-mismatch",
    HTTPStatus.UNPROCESSABLE_CONTENT,
    "Idempotency key reused",
)


class ProblemError(Exception):
    """An error sent to the client as a problem of a named type."""

    def __init__(
        self,
        problem_type: ProblemType,
        detail: str,
        *,
        errors: list[ProblemErrorEntry] | None = None,
        **extensions: ApiModel,
    ) -> None:
        """Describe the problem.

        Args:
            problem_type: The named type of the problem.
            detail: An explanation of this occurrence of the problem.
            errors: The field-level problems, if any.
            **extensions: Extension members, such as ``existing``, named in
                snake_case and sent in camelCase.
        """
        super().__init__(detail)
        self.problem_type = problem_type
        self.detail = detail
        self.errors = errors
        self.extensions = extensions


class ProblemResponse(JSONResponse):
    """A JSON response with the ``application/problem+json`` media type."""

    media_type = "application/problem+json"


def problem_response(
    problem: Problem,
    headers: Mapping[str, str] | None = None,
    extensions: Mapping[str, ApiModel] | None = None,
) -> ProblemResponse:
    """Build the response for a problem, leaving out members that aren't set.

    Args:
        problem: The problem to send.
        headers: Extra response headers, such as ``Allow`` on a 405.
        extensions: Extension members, named in snake_case and sent in
            camelCase, with their own ``null`` values kept.

    Returns:
        The problem as a response with the problem's status.
    """
    body = problem.model_dump(mode="json", by_alias=True, exclude_none=True)
    for name, member in (extensions or {}).items():
        body[to_camel(name)] = member.model_dump(mode="json", by_alias=True)
    return ProblemResponse(body, status_code=problem.status, headers=headers)


def escape_pointer_token(token: str | int) -> str:
    """Escape one reference token of a JSON Pointer (RFC 6901).

    Args:
        token: A field name or list index.

    Returns:
        The token with ``~`` and ``/`` escaped.
    """
    return str(token).replace("~", "~0").replace("/", "~1")


def error_entry(error: Mapping[str, Any]) -> ProblemErrorEntry:
    """Turn one request validation error into an ``errors`` entry.

    Args:
        error: A validation error, as ``RequestValidationError.errors()``
            lists it.

    Returns:
        The entry, with a pointer into the body for a body error, or the
        parameter's name for a query, path or header error.
    """
    source, *location = error["loc"]
    if source != "body":
        return ProblemErrorEntry(detail=error["msg"], parameter=str(location[0]))
    # A body that isn't valid JSON has no fields, so the error is the whole body.
    if error["type"] == "json_invalid":
        location = []
    pointer = "".join(f"/{escape_pointer_token(token)}" for token in location)
    return ProblemErrorEntry(detail=error["msg"], pointer=pointer)


def add_problem_handlers(app: FastAPI) -> None:
    """Make every error the app returns a problem details response.

    Args:
        app: The application to add the handlers to.
    """

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> Response:
        """Send an HTTP error, such as a 403, 404 or 405, as an ``about:blank`` problem.

        Args:
            request: The request that failed.
            exc: The HTTP error raised.

        Returns:
            The problem response, keeping the error's headers.
        """
        try:
            title = HTTPStatus(exc.status_code).phrase
        except ValueError:
            title = "Error"
        problem = Problem(
            title=title,
            status=exc.status_code,
            detail=str(exc.detail),
        )
        return problem_response(problem, exc.headers)

    @app.exception_handler(ProblemError)
    async def handle_problem_error(request: Request, exc: ProblemError) -> Response:
        """Send a problem of a named type.

        Args:
            request: The request that failed.
            exc: The problem raised.

        Returns:
            The problem response, with its errors entries and extension members.
        """
        problem = Problem(
            type=exc.problem_type.uri,
            title=exc.problem_type.title,
            status=exc.problem_type.status,
            detail=exc.detail,
            errors=exc.errors,
        )
        return problem_response(problem, extensions=exc.extensions)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> Response:
        """Send a request validation failure as a validation problem.

        Args:
            request: The request that failed validation.
            exc: The validation failure.

        Returns:
            A 404 problem response if a path parameter is malformed, as every
            path parameter is an id, ahead of any other error; otherwise a 422
            problem response with one ``errors`` entry per error.
        """
        errors = exc.errors()
        if any(error["loc"][0] == "path" for error in errors):
            not_found = HTTPStatus.NOT_FOUND
            problem = Problem(
                title=not_found.phrase, status=not_found, detail=not_found.phrase
            )
            return problem_response(problem)
        problem = Problem(
            type=VALIDATION.uri,
            title=VALIDATION.title,
            status=VALIDATION.status,
            detail="The request isn't valid; see errors for each problem.",
            errors=[error_entry(error) for error in errors],
        )
        return problem_response(problem)

    # A middleware, not an Exception handler, as Starlette re-raises after
    # an Exception handler, so the server would log the error a second time.
    @app.middleware("http")
    async def handle_unexpected_error(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Send an unexpected error as a 500 problem, and log it.

        The response holds no detail of the error, so nothing internal leaks to
        the client.

        Args:
            request: The incoming request.
            call_next: The rest of the app.

        Returns:
            The app's response, or a 500 problem response if it raised.
        """
        try:
            return await call_next(request)
        except Exception:
            logger.exception(
                "Unexpected error in %s %s", request.method, request.url.path
            )
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            problem = Problem(
                title=status.phrase,
                status=status,
                detail="An unexpected error occurred.",
            )
            return problem_response(problem)
