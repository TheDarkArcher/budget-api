"""Documentation of the API's error responses in its OpenAPI document."""

from typing import Any

from app.api.problems import PROBLEM_MEDIA_TYPE
from app.schemas.problems import Problem

JSON_MEDIA_TYPE = "application/json"
SCHEMA_REF_PREFIX = "#/components/schemas/"
# The keys of an OpenAPI path item that hold operations.
HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)


def documented_problem(description: str) -> dict[str, Any]:
    """Describe an error response for a route's or router's ``responses``.

    FastAPI documents the problem schema under the route's own media type;
    ``document_problem_responses`` moves it to ``application/problem+json``.

    Args:
        description: What the error means for the operation, for clients.

    Returns:
        The OpenAPI response, in the form FastAPI's ``responses`` takes.
    """
    return {
        "model": Problem,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {}},
    }


def document_problem_responses(document: dict[str, Any]) -> dict[str, Any]:
    """Document every error response as ``application/problem+json``.

    Responses declared with ``documented_problem`` have their schema moved to
    the problem media type, and FastAPI's own validation error response is
    replaced by the validation problem, with the problem schemas added if no
    operation has defined them. An operation whose only input is its path
    loses that response instead, as a malformed path id returns 404.

    Args:
        document: The OpenAPI document FastAPI generated.

    Returns:
        The same document, changed in place.
    """
    problem_schema = {"$ref": f"{SCHEMA_REF_PREFIX}Problem"}
    validation_schema = {"$ref": f"{SCHEMA_REF_PREFIX}HTTPValidationError"}
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    replaced_validation = False
    for path_item in document.get("paths", {}).values():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            responses = operation.get("responses", {})
            for status, response in list(responses.items()):
                content = response.get("content", {})
                if PROBLEM_MEDIA_TYPE in content:
                    if (schema := content.pop(JSON_MEDIA_TYPE, None)) is not None:
                        content[PROBLEM_MEDIA_TYPE] = schema
                elif content.get(JSON_MEDIA_TYPE, {}).get("schema") == (
                    validation_schema
                ):
                    if has_only_path_input(operation):
                        del responses[status]
                    else:
                        response["content"] = {
                            PROBLEM_MEDIA_TYPE: {"schema": problem_schema}
                        }
                        replaced_validation = True
    if replaced_validation:
        add_problem_schemas(schemas)
    for unused in ("HTTPValidationError", "ValidationError"):
        schemas.pop(unused, None)
    return document


def has_only_path_input(operation: dict[str, Any]) -> bool:
    """Tell whether an OpenAPI operation's only input is its path.

    Args:
        operation: The operation, as FastAPI generated it.

    Returns:
        True if every parameter is in the path and there is no request body.
    """
    parameters = operation.get("parameters", [])
    return "requestBody" not in operation and all(
        parameter["in"] == "path" for parameter in parameters
    )


def add_problem_schemas(schemas: dict[str, Any]) -> None:
    """Add the problem schemas to an OpenAPI document's, unless already there.

    Args:
        schemas: The document's component schemas, changed in place.
    """
    if "Problem" in schemas:
        return
    schema = Problem.model_json_schema(
        ref_template=f"{SCHEMA_REF_PREFIX}{{model}}", mode="serialization"
    )
    added = schema.pop("$defs", {}) | {"Problem": schema}
    # Pydantic documents members that default to None with a null default;
    # the API leaves those members out, as FastAPI's own output says.
    for added_schema in added.values():
        for member in added_schema.get("properties", {}).values():
            if "default" in member and member["default"] is None:
                del member["default"]
    schemas.update(added)
