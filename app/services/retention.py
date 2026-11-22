"""Retention and physical cleanup service (M1 Gate 3)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.delivery import DeliveryRepository
from app.repositories.event import EventRepository
from app.repositories.idempotency import IdempotencyKeyRepository
from app.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)

FIXED_CLEANUP_GRACE_PERIOD_DAYS: int = 7


class RetentionService:
    """Manages event payload retention and physical cleanup lifecycle."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def calculate_cleanup_cutoff(
        self,
        retention_days: int | None = None,
        as_of: datetime | None = None,
    ) -> datetime:
        """Calculate physical cleanup cutoff timestamp.

        Enforces retention range: 1-60 days (default 7 days).
        Physical cleanup occurs after an additional fixed 7-day grace period.
        """
        eff_retention = (
            retention_days if retention_days is not None else self.settings.DEFAULT_RETENTION_DAYS
        )
        if not (1 <= eff_retention <= 60):
            raise ValueError(
                f"Retention days {eff_retention} is invalid. Must be between 1 and 60 days."
            )

        total_days = eff_retention + FIXED_CLEANUP_GRACE_PERIOD_DAYS
        base_time = as_of or datetime.now(UTC)
        return base_time - timedelta(days=total_days)

    async def purge_expired_records(
        self,
        session: AsyncSession,
        retention_days: int | None = None,
        batch_size: int = 100,
        as_of: datetime | None = None,
    ) -> dict[str, int]:
        """Physically delete expired events, deliveries, outbox, and retired keys.

        Respects the total retention period (retention + grace period) and executes
        deletions in strict foreign-key dependency order to maintain relational integrity.
        """
        cutoff = self.calculate_cleanup_cutoff(
            retention_days=retention_days,
            as_of=as_of,
        )

        event_repo = EventRepository(session)
        outbox_repo = OutboxRepository(session)
        delivery_repo = DeliveryRepository(session)
        idempotency_repo = IdempotencyKeyRepository(session)

        # 1. Identify expired events
        expired_event_ids = await event_repo.get_expired_ids(cutoff=cutoff, limit=batch_size)

        purged_outbox = 0
        purged_deliveries = 0
        purged_events = 0

        if expired_event_ids:
            # 2. Break deferred FK reference from idempotency_keys to events
            await idempotency_repo.clear_event_id_for_events(expired_event_ids)

            # 3. Purge child Outbox entries
            purged_outbox = await outbox_repo.delete_by_event_ids(expired_event_ids)

            # 4. Purge child Delivery entries
            purged_deliveries = await delivery_repo.delete_by_event_ids(expired_event_ids)

            # 5. Purge expired Events
            purged_events = await event_repo.delete_by_ids(expired_event_ids)

        # 6. Purge retired IdempotencyKeys that have passed retention + grace period
        purged_keys = await idempotency_repo.purge_retired_keys(before=cutoff)

        if purged_events > 0 or purged_keys > 0:
            await session.commit()
            logger.info(
                "Purged expired records: %d events, %d deliveries, %d outbox, %d keys",
                purged_events,
                purged_deliveries,
                purged_outbox,
                purged_keys,
            )

        return {
            "purged_events": purged_events,
            "purged_deliveries": purged_deliveries,
            "purged_outbox": purged_outbox,
            "purged_keys": purged_keys,
        }


retention_service = RetentionService()
