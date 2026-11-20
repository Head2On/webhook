"""Health and system inspection service."""

from app.core.config import get_settings
from app.db.session import check_database_connection
from app.integrations.redis import redis_client
from app.schemas.health import HealthResponse, ReadinessResponse


class HealthService:
    """Service orchestrating system health and readiness checks."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def get_liveness(self) -> HealthResponse:
        """Provide simple process liveness status."""
        return HealthResponse(
            status="ok",
            environment=self.settings.ENVIRONMENT,
            version="0.1.0",
        )

    async def get_readiness(self) -> ReadinessResponse:
        """Provide infrastructure readiness status for database and cache."""
        try:
            db_ok = await check_database_connection()
            db_status = "connected" if db_ok else "unhealthy"
        except Exception:
            db_status = "unavailable"

        redis_ok = await redis_client.ping()
        redis_status = "connected" if redis_ok else "unavailable"

        overall_status = "ok" if db_status == "connected" else "degraded"

        return ReadinessResponse(
            status=overall_status,
            environment=self.settings.ENVIRONMENT,
            version="0.1.0",
            database=db_status,
            redis=redis_status,
        )


health_service = HealthService()
