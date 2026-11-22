"""Application configuration and validation using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings schema with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: Literal["development", "testing", "production"] = Field(
        default="development",
        description="Current deployment environment",
    )
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode (disallowed in production)",
    )
    PROJECT_NAME: str = Field(
        default="HookRelay",
        description="Application service name",
    )
    API_V1_PREFIX: str = Field(
        default="/api/v1",
        description="Prefix for v1 API routes",
    )

    # Server & Logging
    HOST: str = Field(default="0.0.0.0", description="Bind host")
    PORT: int = Field(default=8000, ge=1, le=65535, description="Bind port")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    # Database
    DATABASE_URL: PostgresDsn = Field(
        ...,
        description="PostgreSQL connection string with async driver",
    )
    TEST_DATABASE_URL: PostgresDsn | None = Field(
        default=None,
        description="Optional isolated PostgreSQL connection string for integration tests",
    )
    DATABASE_POOL_SIZE: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Database connection pool size",
    )
    DATABASE_MAX_OVERFLOW: int = Field(
        default=20,
        ge=0,
        le=100,
        description="Max overflow connections beyond pool size",
    )
    DATABASE_POOL_TIMEOUT: int = Field(
        default=30,
        ge=1,
        description="Pool timeout in seconds",
    )

    # M1 Gate 3: Idempotency, Retention & Ingestion
    DEFAULT_RETENTION_DAYS: int = Field(
        default=7,
        ge=1,
        le=60,
        description="Default idempotency key retention in days (1-60 days)",
    )
    CLEANUP_GRACE_PERIOD_DAYS: int = Field(
        default=7,
        frozen=True,
        description="Fixed 7-day grace period before physical cleanup",
    )
    POSTGRES_LOCK_TIMEOUT_SECONDS: float = Field(
        default=2.0,
        ge=0.1,
        le=30.0,
        description="Bounded PostgreSQL transaction lock timeout in seconds",
    )
    MAX_PAYLOAD_SIZE_BYTES: int = Field(
        default=1_048_576,  # 1 MiB exactly
        description="Maximum incoming webhook payload size in bytes (1 MiB)",
    )

    # Redis (Integration boundary)
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    REDIS_POOL_SIZE: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Redis connection pool size",
    )
    REDIS_OUTBOX_STREAM: str = Field(
        default="hookrelay:outbox:stream",
        description="Redis stream name for outbox event notifications",
    )

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def validate_database_scheme(cls, v: PostgresDsn) -> PostgresDsn:
        """Ensure database scheme uses an async-compatible driver."""
        scheme = v.scheme
        if scheme not in ("postgresql+psycopg", "postgresql+asyncpg"):
            # If user passed plain postgresql://, we require explicit driver scheme
            raise ValueError(
                f"DATABASE_URL scheme '{scheme}' is invalid. "
                "Must be 'postgresql+psycopg' or 'postgresql+asyncpg'."
            )
        return v

    @model_validator(mode="after")
    def validate_production_constraints(self) -> Settings:
        """Strict checks for production safety."""
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                raise ValueError("DEBUG mode must be disabled in production")
            hosts = self.DATABASE_URL.hosts()
            if any(h.get("host") in ("localhost", "127.0.0.1") for h in hosts):
                raise ValueError("DATABASE_URL cannot point to localhost in production")
        return self

    @property
    def sync_database_url(self) -> str:
        """Return synchronous database URL for Alembic migrations."""
        url = str(self.DATABASE_URL)
        if url.startswith("postgresql+psycopg://"):
            return url.replace("postgresql+psycopg://", "postgresql://", 1)
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()  # type: ignore[call-arg]
