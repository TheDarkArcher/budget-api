"""Schemas for the health endpoints."""

from enum import StrEnum

from app.schemas.base import ApiModel


class HealthStatus(StrEnum):
    """Status of the app or one of its subsystems."""

    OK = "ok"
    ERROR = "error"


class CheckResult(ApiModel):
    """Result of a single subsystem check."""

    status: HealthStatus
    latency_ms: int | None = None
    error: str | None = None


class LivenessResponse(ApiModel):
    """Whether the app process is up and serving requests."""

    status: HealthStatus
    version: str
    build: str | None = None


class ReadinessResponse(ApiModel):
    """Whether the app and each subsystem it depends on are ready."""

    status: HealthStatus
    version: str
    build: str | None = None
    checks: dict[str, CheckResult]
