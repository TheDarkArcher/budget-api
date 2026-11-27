"""Base models shared by the API schemas."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base for API schemas: snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RequestBody(ApiModel):
    """Base for request bodies, and for the objects nested in them.

    A field the model doesn't declare is refused rather than ignored.
    Response and query parameter models extend `ApiModel`, which ignores
    undeclared fields.
    """

    model_config = ConfigDict(extra="forbid")
