"""Assertions shared by tests of problem details (RFC 9457) responses."""

from typing import Any

from httpx2 import Response

PROBLEM_JSON = "application/problem+json"
# The body of every 404, whether the path is unknown or names no record.
NOT_FOUND_PROBLEM = {
    "type": "about:blank",
    "title": "Not Found",
    "status": 404,
    "detail": "Not Found",
}


def assert_problem(response: Response, status: int) -> dict[str, Any]:
    """Check the response is a problem with the given status and return its body."""
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_JSON
    body: dict[str, Any] = response.json()
    return body


def without_error_details(problem_body: dict[str, Any]) -> dict[str, Any]:
    """Check every ``errors`` entry has a detail and return the body without them.

    The details are Pydantic's messages, so tests compare the rest of the body.
    """
    errors = []
    for error in problem_body["errors"]:
        assert isinstance(error.get("detail"), str)
        errors.append({key: value for key, value in error.items() if key != "detail"})
    return {**problem_body, "errors": errors}
