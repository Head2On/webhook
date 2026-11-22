"""Repository for Delivery entity operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import Delivery
from app.repositories.base import BaseRepository


class DeliveryRepository(BaseRepository[Delivery]):
    """Database repository managing Delivery persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        project_id: uuid.UUID,
        event_id: uuid.UUID,
        status: str = "pending",
        created_at: datetime | None = None,
    ) -> Delivery:
        """Create an initial Delivery record for an accepted Event."""
        delivery = Delivery(
            id=uuid.uuid4(),
            project_id=project_id,
            event_id=event_id,
            status=status,
            attempt_count=0,
            created_at=created_at or datetime.now(),
        )
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def get_by_event_id(self, event_id: uuid.UUID) -> list[Delivery]:
        """Fetch all delivery records associated with an event."""
        stmt = select(Delivery).where(Delivery.event_id == event_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
