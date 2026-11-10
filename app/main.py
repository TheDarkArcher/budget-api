"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, v1
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    The OpenAPI schema it serves reports the build label as its version when
    one is set, so a running app's schema identifies its exact build.

    Returns:
        The configured FastAPI application.

    Raises:
        pydantic.ValidationError: If the settings are missing or invalid.
    """
    settings = get_settings()
    app = FastAPI(title="Budget Tracker API", version=settings.app_build or __version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Location"],
    )
    app.include_router(health.router)
    app.include_router(v1.router)
    return app
