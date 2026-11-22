"""Redis integration boundary isolating Redis infrastructure."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from redis.asyncio import ConnectionPool, Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Encapsulated Redis integration boundary."""

    def __init__(self, url: str | None = None, max_connections: int | None = None) -> None:
        settings = get_settings()
        self._url = url or settings.REDIS_URL
        self._max_connections = max_connections or settings.REDIS_POOL_SIZE
        self._outbox_stream = settings.REDIS_OUTBOX_STREAM
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

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a Redis channel."""
        try:
            client = self._get_client()
            return int(await client.publish(channel, message))
        except Exception as exc:
            logger.warning("Redis publish to channel '%s' failed: %s", channel, exc)
            return 0

    async def xadd(
        self,
        stream: str,
        fields: dict[str, Any],
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str | None:
        """Append an entry to a Redis Stream."""
        try:
            client = self._get_client()
            str_fields: dict[Any, Any] = {str(k): str(v) for k, v in fields.items()}
            res = await client.xadd(stream, str_fields, maxlen=maxlen, approximate=approximate)
            return str(res) if res is not None else None
        except Exception as exc:
            logger.warning("Redis xadd to stream '%s' failed: %s", stream, exc)
            return None

    async def signal_outbox_event(
        self,
        event_id: uuid.UUID | str,
        project_id: uuid.UUID | str,
        event_type: str,
    ) -> bool:
        """Signal downstream delivery workers that a new outbox event is ready.

        Emits event notification to Redis stream to prevent workers from having
        to poll PostgreSQL by default.
        """
        payload = {
            "event_id": str(event_id),
            "project_id": str(project_id),
            "event_type": event_type,
        }
        res = await self.xadd(self._outbox_stream, payload)
        return res is not None

    async def close(self) -> None:
        """Close connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None


redis_client = RedisClient()
