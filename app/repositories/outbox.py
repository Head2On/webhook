"""Repository for Outbox entity operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import Outbox
from app.repositories.base import BaseRepository


class OutboxRepository(BaseRepository[Outbox]):
    """Database repository managing transactional Outbox persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        event_id: uuid.UUID,
        payload: dict[str, Any] | None = None,
        status: str = "pending",
        created_at: datetime | None = None,
    ) -> Outbox:
        """Create an Outbox entry within the current transaction."""
        outbox = Outbox(
            id=uuid.uuid4(),
            event_id=event_id,
            status=status,
            payload=payload,
            created_at=created_at or datetime.now(),
        )
        self.session.add(outbox)
        await self.session.flush()
        return outbox

    async def get_by_event_id(self, event_id: uuid.UUID) -> list[Outbox]:
        """Fetch all outbox records associated with an event."""
        stmt = select(Outbox).where(Outbox.event_id == event_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
