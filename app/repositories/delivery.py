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

    async def update_status(
        self,
        delivery_id: uuid.UUID,
        status: str,
        next_attempt_at: datetime | None = None,
    ) -> None:
        """Update delivery record status and attempt details."""
        from typing import Any

        from sqlalchemy import update

        values: dict[str, Any] = {
            "status": status,
            "attempt_count": Delivery.attempt_count + 1,
        }
        if next_attempt_at is not None:
            values["next_attempt_at"] = next_attempt_at

        stmt = update(Delivery).where(Delivery.id == delivery_id).values(**values)
        await self.session.execute(stmt)

    async def get_pending_by_project(
        self,
        project_id: uuid.UUID,
        limit: int = 100,
    ) -> list[Delivery]:
        """Fetch pending deliveries for a specific project."""
        stmt = (
            select(Delivery)
            .where(
                Delivery.project_id == project_id,
                Delivery.status == "pending",
            )
            .order_by(Delivery.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_event_ids(self, event_ids: list[uuid.UUID]) -> int:
        """Delete deliveries associated with the specified event IDs."""
        if not event_ids:
            return 0
        from sqlalchemy import delete

        stmt = delete(Delivery).where(Delivery.event_id.in_(event_ids))
        result = await self.session.execute(stmt)
        return int(getattr(result, "rowcount", 0))
