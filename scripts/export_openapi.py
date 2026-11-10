"""Write the API's OpenAPI schema to ``openapi.json`` for committing.

Re-run it with ``uv run poe export-openapi`` whenever an endpoint or schema
changes, so it uses the project's current version and dependencies rather
than whatever a stale environment has installed. Building the schema never
connects to the database, but the app's settings still need ``DATABASE_URL``
to be set, as it is in ``.env``.
"""

import json
import logging
from pathlib import Path

from app import __version__
from app.core.config import get_settings
from app.main import create_app

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "openapi.json"


def openapi_json() -> str:
    """Render the app's OpenAPI schema as JSON.

    The output is the same on every run for the same code, so the committed
    file only changes when the API does. It always has the plain version, even
    when a build label is set, which the running app would report instead.

    Returns:
        The schema, indented, with a trailing newline.
    """
    app = create_app()
    app.version = __version__
    schema = app.openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def export(path: Path = OPENAPI_PATH) -> None:
    """Write the app's OpenAPI schema to a file, with Unix line endings.

    Args:
        path: The file to write, ``openapi.json`` at the repository root by
            default.
    """
    path.write_text(openapi_json(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    logging.basicConfig(
        level=get_settings().log_level, format="%(levelname)s %(message)s"
    )
    export()
    logger.info("Wrote %s", OPENAPI_PATH.relative_to(ROOT))
