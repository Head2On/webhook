"""Repository for Event entity operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import Event
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    """Database repository managing Event persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        project_id: uuid.UUID,
        idempotency_key_id: uuid.UUID,
        event_type: str,
        raw_payload_bytes: bytes,
        payload_hash: str,
        created_at: datetime,
    ) -> Event:
        """Create and persist an Event record with raw byte fidelity."""
        event = Event(
            id=uuid.uuid4(),
            project_id=project_id,
            idempotency_key_id=idempotency_key_id,
            event_type=event_type,
            raw_payload_bytes=raw_payload_bytes,
            payload_hash=payload_hash,
            created_at=created_at,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, event_id: uuid.UUID) -> Event | None:
        """Retrieve an Event by primary key."""
        stmt = select(Event).where(Event.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
