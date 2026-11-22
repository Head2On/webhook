"""Repository for IdempotencyKey entity operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyKey
from app.repositories.base import BaseRepository


class IdempotencyKeyRepository(BaseRepository[IdempotencyKey]):
    """Database repository managing IdempotencyKey persistence and locking."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active(
        self,
        project_id: uuid.UUID,
        idempotency_key: str,
    ) -> IdempotencyKey | None:
        """Fetch active (non-retired) idempotency key record for a project."""
        stmt = select(IdempotencyKey).where(
            IdempotencyKey.project_id == project_id,
            IdempotencyKey.idempotency_key == idempotency_key,
            IdempotencyKey.retired_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def lock_expired_for_update(
        self,
        key_id: uuid.UUID,
        as_of: datetime,
    ) -> IdempotencyKey | None:
        """Acquire row-level exclusive lock on an expired unretired key row.

        Must satisfy: expires_at <= as_of AND retired_at IS NULL.
        """
        stmt = (
            select(IdempotencyKey)
            .where(
                IdempotencyKey.id == key_id,
                IdempotencyKey.expires_at <= as_of,
                IdempotencyKey.retired_at.is_(None),
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def retire(
        self,
        key_id: uuid.UUID,
        retired_at: datetime,
    ) -> None:
        """Mark an expired idempotency key record as retired."""
        stmt = (
            update(IdempotencyKey).where(IdempotencyKey.id == key_id).values(retired_at=retired_at)
        )
        await self.session.execute(stmt)

    async def create_claim(
        self,
        project_id: uuid.UUID,
        idempotency_key: str,
        fingerprint: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> IdempotencyKey:
        """Insert an initial idempotency key claim prior to event creation."""
        claim = IdempotencyKey(
            id=uuid.uuid4(),
            project_id=project_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            created_at=created_at,
            expires_at=expires_at,
            retired_at=None,
        )
        self.session.add(claim)
        await self.session.flush()
        return claim

    async def complete_claim(
        self,
        claim: IdempotencyKey,
        event_id: uuid.UUID,
        response_status_code: int,
        response_body: dict[str, Any],
        response_headers: dict[str, Any] | None = None,
    ) -> None:
        """Update idempotency key with created event ID and response payload."""
        claim.event_id = event_id
        claim.response_status_code = response_status_code
        claim.response_body = response_body
        claim.response_headers = response_headers
        await self.session.flush()

    async def clear_event_id_for_events(self, event_ids: list[uuid.UUID]) -> int:
        """Disassociate event references to satisfy deferred FK constraints before deletion."""
        if not event_ids:
            return 0
        stmt = (
            update(IdempotencyKey)
            .where(IdempotencyKey.event_id.in_(event_ids))
            .values(event_id=None)
        )
        result = await self.session.execute(stmt)
        return int(getattr(result, "rowcount", 0))

    async def delete_by_ids(self, key_ids: list[uuid.UUID]) -> int:
        """Delete idempotency keys by primary key list."""
        if not key_ids:
            return 0
        from sqlalchemy import delete

        stmt = delete(IdempotencyKey).where(IdempotencyKey.id.in_(key_ids))
        result = await self.session.execute(stmt)
        return int(getattr(result, "rowcount", 0))

    async def purge_retired_keys(self, before: datetime) -> int:
        """Physically delete idempotency keys that were retired before the given threshold."""
        from sqlalchemy import delete

        stmt = delete(IdempotencyKey).where(
            IdempotencyKey.retired_at.is_not(None),
            IdempotencyKey.retired_at < before,
        )
        result = await self.session.execute(stmt)
        return int(getattr(result, "rowcount", 0))
