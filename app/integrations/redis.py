"""Redis integration boundary isolating Redis infrastructure."""

import logging

from redis.asyncio import ConnectionPool, Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Encapsulated Redis integration boundary."""

    def __init__(self, url: str | None = None, max_connections: int | None = None) -> None:
        settings = get_settings()
        self._url = url or settings.REDIS_URL
        self._max_connections = max_connections or settings.REDIS_POOL_SIZE
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    def _get_client(self) -> Redis:
        if self._client is None:
            self._pool = ConnectionPool.from_url(
                self._url,
                max_connections=self._max_connections,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )
            self._client = Redis(connection_pool=self._pool)
        return self._client

    async def ping(self) -> bool:
        """Ping Redis instance to check availability."""
        try:
            client = self._get_client()
            return bool(await client.ping())
        except Exception as exc:
            logger.warning("Redis ping failed: %s", exc)
            return False

    async def close(self) -> None:
        """Close connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None


redis_client = RedisClient()
