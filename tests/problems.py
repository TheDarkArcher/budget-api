"""Checks and expected bodies for tests of problem details (RFC 9457)."""

from typing import Any

import pytest
from httpx2 import Response

PROBLEM_JSON = "application/problem+json"
# The body of every 404, whether the path is unknown or names no record.
NOT_FOUND_PROBLEM = {
    "type": "about:blank",
    "title": "Not Found",
    "status": 404,
    "detail": "Not Found",
}
# The body of every 403, sent when there is no current user.
FORBIDDEN_PROBLEM = {
    "type": "about:blank",
    "title": "Forbidden",
    "status": 403,
    "detail": "Not authorised",
}
# The body of every 500, whatever went wrong.
INTERNAL_ERROR_PROBLEM = {
    "type": "about:blank",
    "title": "Internal Server Error",
    "status": 500,
    "detail": "An unexpected error occurred.",
}
# The body of every 409 for changing an archived record, whatever the resource.
ARCHIVED_PROBLEM = {
    "type": "/problems/archived",
    "title": "Record archived",
    "status": 409,
    "detail": "The record is archived; unarchive it before changing it.",
}
# The body of every 409 for deleting a record a transaction uses.
IN_USE_TRANSACTION_PROBLEM = {
    "type": "/problems/in-use/transaction",
    "title": "In use by a transaction",
    "status": 409,
    "detail": "A transaction uses the record, so it can't be deleted;"
    " archive it instead.",
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


def assert_exception_logged(caplog: pytest.LogCaptureFixture, text: str) -> None:
    """Check a log record carries an exception whose message contains ``text``."""
    assert any(
        record.exc_info is not None and text in str(record.exc_info[1])
        for record in caplog.records
    )


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


def expected_name_conflict_problem(
    resource: str, existing: dict[str, Any]
) -> dict[str, Any]:
    """The name conflict a resource returns, naming the record that has the name.

    ``existing`` is that record's nested reference, as the response carries it.
    """
    return {
        "type": "/problems/name-conflict",
        "title": "Name already in use",
        "status": 409,
        "detail": f"A {resource} named '{existing['name']}' already exists.",
        "existing": existing,
    }
