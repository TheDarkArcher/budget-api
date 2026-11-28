"""Tests that the operations in the committed ``openapi.json`` follow conventions."""

import json
import re
from collections.abc import Iterator
from typing import Any

import pytest

from export_openapi import OPENAPI_PATH

# The singular of each resource's path segment, for the operation id vocabulary.
SINGULARS = {
    "payees": "Payee",
    "tags": "Tag",
    "transaction-categories": "TransactionCategory",
    "item-categories": "ItemCategory",
    "items": "Item",
    "transactions": "Transaction",
    "sizes": "Size",
}
# Operations outside the vocabulary, named after what they return.
NAMED_BY_HAND = {
    ("get", "/health/live"): "getLiveness",
    ("get", "/health/ready"): "getReadiness",
    ("get", "/api/v1/me"): "getCurrentUser",
    ("get", "/api/v1/transactions/summary"): "getTransactionSummary",
}
ACTIONS = {"archive", "unarchive"}
DOCSTRING_SECTIONS = re.compile(
    r"^\s*(Args|Arguments|Attributes|Returns|Yields|Raises):", re.MULTILINE
)
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
VERSIONED_API_PATH = re.compile(r"^/api/v\d+(/|$)")
CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
PROBLEM_CONTENT = {
    "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
}
DOCUMENT: dict[str, Any] = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
OPERATIONS = [
    pytest.param(method, path, operation, id=f"{method} {path}")
    for path, path_item in DOCUMENT["paths"].items()
    for method, operation in path_item.items()
    if method in HTTP_METHODS
]


def segments(path: str) -> list[str]:
    return VERSIONED_API_PATH.sub("/", path).strip("/").split("/")


def is_placeholder(segment: str) -> bool:
    return segment.startswith("{")


def pascal_case(segment: str) -> str:
    return "".join(word.capitalize() for word in segment.split("-"))


def singular(segment: str) -> str:
    assert segment in SINGULARS, f"add {segment!r} to SINGULARS"
    return SINGULARS[segment]


def expected_operation_id(method: str, path: str) -> str | None:
    if (method, path) in NAMED_BY_HAND:
        return NAMED_BY_HAND[method, path]
    match segments(path), method:
        case [resource], "get":
            return f"list{pascal_case(resource)}"
        case [resource], "post":
            return f"create{singular(resource)}"
        case [resource, record], "get" | "put" | "delete" if is_placeholder(record):
            verb = {"get": "get", "put": "update", "delete": "delete"}[method]
            return f"{verb}{singular(resource)}"
        case [resource, record, action], "post" if (
            is_placeholder(record) and action in ACTIONS
        ):
            return f"{action}{singular(resource)}"
        case [resource, record, subresource], "get" if is_placeholder(record):
            return f"list{singular(resource)}{pascal_case(subresource)}"
    return None


def descriptions(node: Any, location: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                yield location, value
            yield from descriptions(value, f"{location}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from descriptions(value, f"{location}/{index}")


def expected_problem_statuses(path: str, operation: dict[str, Any]) -> set[str]:
    expected = set()
    if VERSIONED_API_PATH.match(path):
        expected.add("403")
    locations = {parameter["in"] for parameter in operation.get("parameters", [])}
    # A malformed path id returns 404, so only other input can return 422.
    if "path" in locations:
        expected.add("404")
    if locations & {"query", "header"} or "requestBody" in operation:
        expected.add("422")
    return expected


@pytest.mark.parametrize(("method", "path", "operation"), OPERATIONS)
def test_operation_id_follows_the_vocabulary(
    method: str, path: str, operation: dict[str, Any]
) -> None:
    expected = expected_operation_id(method, path)
    assert expected is not None, "no vocabulary rule; name it by hand"
    assert operation.get("operationId") == expected


def test_descriptions_are_written_for_clients() -> None:
    with_sections = {
        location: text
        for location, text in descriptions(DOCUMENT)
        if DOCSTRING_SECTIONS.search(text)
    }
    assert with_sections == {}


@pytest.mark.parametrize(("method", "path", "operation"), OPERATIONS)
def test_operation_declares_its_responses(
    method: str, path: str, operation: dict[str, Any]
) -> None:
    responses = operation["responses"]
    for status in expected_problem_statuses(path, operation):
        assert responses.get(status, {}).get("content") == PROBLEM_CONTENT, status
    if method == "post" and len(segments(path)) == 1:
        created = responses.get("201", {}).get("headers", {})
        assert "Location" in created, "a create returns 201 with a Location header"
    if method == "delete":
        assert "204" in responses


@pytest.mark.parametrize(("method", "path", "operation"), OPERATIONS)
def test_path_parameters_are_camel_case(
    method: str, path: str, operation: dict[str, Any]
) -> None:
    names = [
        parameter["name"]
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "path"
    ]
    assert [name for name in names if not CAMEL_CASE.match(name)] == []
