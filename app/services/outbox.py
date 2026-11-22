"""Outbox dispatch and reconciliation service (M1 Gate 3)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.integrations.redis import RedisClient, redis_client
from app.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)


class OutboxDispatcherService:
    """Manages transactional Outbox dispatch and fallback reconciliation."""

    def __init__(
        self,
        redis_override: RedisClient | None = None,
    ) -> None:
        self.settings = get_settings()
        self.redis = redis_override or redis_client

    async def dispatch_pending_batch(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> int:
        """Fetch and signal pending outbox records to ensure reliable at-least-once delivery.

        Acts as fallback / reconciliation worker to guarantee that events whose
        initial post-commit signal was interrupted are dispatched without tight polling.
        """
        outbox_repo = OutboxRepository(session)
        pending = await outbox_repo.get_pending(limit=limit)
        if not pending:
            return 0

        dispatched_count = 0
        now = datetime.now(UTC)

        for entry in pending:
            payload = entry.payload or {}
            event_id = payload.get("event_id") or str(entry.event_id)
            project_id = payload.get("project_id", str(uuid.uuid4()))
            event_type = payload.get("event_type", "webhook.dispatched")

            # Signal Redis stream for worker consumption
            signaled = await self.redis.signal_outbox_event(
                event_id=event_id,
                project_id=project_id,
                event_type=event_type,
            )

            if signaled:
                await outbox_repo.mark_dispatched(entry.id, processed_at=now)
                dispatched_count += 1
            else:
                logger.warning(
                    "Failed to signal outbox entry %s; leaving pending for next pass",
                    entry.id,
                )

        if dispatched_count > 0:
            await session.commit()

        return dispatched_count


outbox_dispatcher = OutboxDispatcherService()
