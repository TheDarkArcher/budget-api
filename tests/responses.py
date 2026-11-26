"""Helpers shared by tests of the API's success responses."""

from datetime import datetime
from typing import Any

import httpx2


def response_parts(response: httpx2.Response) -> tuple[int, str, bytes]:
    """Return what a replay must repeat: the status, ``Location`` and body."""
    return response.status_code, response.headers["location"], response.content


def with_parsed_archive_time(body: dict[str, Any]) -> dict[str, Any]:
    """Return the body with ``archivedAt`` parsed, to compare it as a time."""
    archived_at = datetime.fromisoformat(body["archivedAt"])
    return {**body, "archivedAt": archived_at}
