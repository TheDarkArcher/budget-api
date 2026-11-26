"""FastAPI application factory."""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, v1
from app.api.current_user import ConnectionOpener, CurrentUserMiddleware
from app.api.openapi import document_problem_responses
from app.api.problems import add_problem_handlers
from app.core.config import get_settings
from app.database import engine


class BudgetAPI(FastAPI):
    """The application, with its error responses documented as problem details."""

    def openapi(self) -> dict[str, Any]:
        """Generate the OpenAPI schema once, documenting errors as problems.

        Returns:
            The OpenAPI schema.
        """
        if self.openapi_schema is None:
            self.openapi_schema = document_problem_responses(super().openapi())
        return self.openapi_schema


def create_app(open_connection: ConnectionOpener = engine.open_connection) -> FastAPI:
    """Create and configure the FastAPI application.

    The OpenAPI schema it serves reports the build label as its version when
    one is set, so a running app's schema identifies its exact build.

    Args:
        open_connection: Opens each request's connection and transaction;
            tests pass one that opens a savepoint instead.

    Returns:
        The configured FastAPI application.

    Raises:
        pydantic.ValidationError: If the settings are missing or invalid.
    """
    settings = get_settings()
    app = BudgetAPI(
        title="Budget Tracker API", version=settings.app_build or __version__
    )
    # Middleware added later wraps what was added before. The problem
    # handlers wrap the resolver, so its failures become 500 problems, and
    # CORS wraps both, so preflights skip the resolver and every problem is
    # readable by the frontend too.
    app.add_middleware(CurrentUserMiddleware, open_connection=open_connection)
    add_problem_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key"],
        expose_headers=["Location"],
    )
    app.include_router(health.router)
    app.include_router(v1.router)
    return app
