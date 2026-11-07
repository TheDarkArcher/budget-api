"""Application settings."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import PositiveInt, PostgresDsn, Secret, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Settings read from environment variables and the ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    database_url: Secret[PostgresDsn]
    database_pool_timeout: PositiveInt = 5
    database_statement_timeout: PositiveInt = 30
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: LogLevel = "INFO"
    app_build: str | None = None

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        """Split a comma-separated string of origins into a list.

        Args:
            value: The raw value from the environment.

        Returns:
            A list of origins, or the value unchanged if it isn't a string.
        """
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Load the settings once and reuse them.

    Returns:
        The application settings.
    """
    return Settings()
