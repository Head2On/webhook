"""Health check response schemas."""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Schema for basic liveness probe response."""

    model_config = ConfigDict(frozen=True)

    status: str
    environment: str
    version: str


class ReadinessResponse(BaseModel):
    """Schema for dependency readiness probe response."""

    model_config = ConfigDict(frozen=True)

    status: str
    environment: str
    version: str
    database: str
    redis: str
