"""Checks and expected bodies for tests of problem details (RFC 9457)."""

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
# The body of every 409 for changing an archived record, whatever the resource.
ARCHIVED_PROBLEM = {
    "type": "/problems/archived",
    "title": "Record archived",
    "status": 409,
    "detail": "The record is archived; unarchive it before changing it.",
}
# The body of every validation problem, apart from its errors entries.
VALIDATION_PROBLEM = {
    "type": "/problems/validation",
    "title": "Validation failed",
    "status": 422,
    "detail": "The request isn't valid; see errors for each problem.",
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


def body_validation_problem(*pointers: str) -> dict[str, Any]:
    """The validation problem for errors at these body pointers, details removed."""
    return {
        **VALIDATION_PROBLEM,
        "errors": [{"pointer": pointer} for pointer in pointers],
    }


def parameter_validation_problem(*parameters: str) -> dict[str, Any]:
    """The validation problem for errors in these parameters, details removed."""
    return {
        **VALIDATION_PROBLEM,
        "errors": [{"parameter": parameter} for parameter in parameters],
    }
