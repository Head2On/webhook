"""Idempotency and durable ingestion transaction engine (M1 Gate 3)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.core.config import get_settings
from app.core.exceptions import (
    IdempotencyFingerprintMismatchError,
)
from app.models.idempotency import IdempotencyKey
from app.repositories.delivery import DeliveryRepository
from app.repositories.event import EventRepository
from app.repositories.idempotency import IdempotencyKeyRepository
from app.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    """Represents the outcome of a webhook ingestion attempt."""

    status_code: int
    event_id: uuid.UUID
    idempotency_key: str
    fingerprint: str
    is_replay: bool
    response_body: dict[str, Any]
    response_headers: dict[str, str]


class IdempotencyService:
    """Manages transactional idempotency lifecycle, concurrency recovery, and persistence."""

    def __init__(self, settings_override: Any = None) -> None:
        self.settings = settings_override or get_settings()

    async def process_ingestion(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        idempotency_key: str,
        event_type: str,
        raw_payload_bytes: bytes,
        fingerprint: str,
        retention_days: int | None = None,
    ) -> IngestionResult:
        """Process webhook ingestion with strict PostgreSQL idempotency semantics.

        - New Key -> Creates IdempotencyKey, Event, Delivery, Outbox and returns HTTP 202.
        - Existing Key + Identical Fingerprint -> Returns HTTP 200 with original acceptance payload.
        - Existing Key + Different Fingerprint -> Raises HTTP 409 conflict.
        - Concurrency Conflict (23505) -> Rollback, re-read winning record (Never HTTP 500).
        """
        # 1. Enforce bounded PostgreSQL lock timeout
        lock_timeout_ms = int(self.settings.POSTGRES_LOCK_TIMEOUT_SECONDS * 1000)
        await session.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout_ms}ms'"))

        now = datetime.now(UTC)
        retention = (
            retention_days if retention_days is not None else self.settings.DEFAULT_RETENTION_DAYS
        )
        expires_at = now + timedelta(days=retention)

        repo = IdempotencyKeyRepository(session)
        active_key = await repo.get_active(project_id, idempotency_key)

        # 2. Check if active record exists
        if active_key is not None:
            # Check expiry boundary: active if expires_at > now, expired if expires_at <= now
            if active_key.expires_at <= now:
                # Expired key replacement protocol (Doc 02 §4)
                locked_key = await repo.lock_expired_for_update(active_key.id, now)
                if locked_key is not None:
                    # Winner acquires lock and retires the expired record
                    await repo.retire(locked_key.id, now)
                    logger.info(
                        "Retired expired idempotency key %s for project %s",
                        idempotency_key,
                        project_id,
                    )
                else:
                    # Competing transaction already retired/replaced it; re-read winning row
                    await session.rollback()
                    return await self._handle_concurrency_conflict(
                        session=session,
                        project_id=project_id,
                        idempotency_key=idempotency_key,
                        event_type=event_type,
                        raw_payload_bytes=raw_payload_bytes,
                        incoming_fingerprint=fingerprint,
                        retention_days=retention_days,
                    )
            else:
                # Active non-expired key: evaluate fingerprint
                return self._evaluate_active_key(active_key, idempotency_key, fingerprint)

        # 3. Create fresh claim and associated durable entities
        try:
            # Step A: Insert initial idempotency claim (event_id deferred)
            claim = await repo.create_claim(
                project_id=project_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expires_at=expires_at,
                created_at=now,
            )

            # Step B: Insert Event with raw BYTEA payload
            event_repo = EventRepository(session)
            event = await event_repo.create(
                project_id=project_id,
                idempotency_key_id=claim.id,
                event_type=event_type,
                raw_payload_bytes=raw_payload_bytes,
                payload_hash=fingerprint,
                created_at=now,
            )

            # Step C: Insert initial Delivery record
            delivery_repo = DeliveryRepository(session)
            await delivery_repo.create(
                project_id=project_id,
                event_id=event.id,
                status="pending",
                created_at=now,
            )

            # Step D: Insert Transactional Outbox record
            outbox_repo = OutboxRepository(session)
            await outbox_repo.create(
                event_id=event.id,
                payload={
                    "event_id": str(event.id),
                    "project_id": str(project_id),
                    "event_type": event_type,
                    "idempotency_key": idempotency_key,
                    "fingerprint": fingerprint,
                },
                status="pending",
                created_at=now,
            )

            # Step E: Update IdempotencyKey with event_id and response body
            response_body = {
                "event_id": str(event.id),
                "status": "accepted",
                "idempotency_key": idempotency_key,
                "fingerprint": fingerprint,
                "created_at": now.isoformat(),
            }
            await repo.complete_claim(
                claim=claim,
                event_id=event.id,
                response_status_code=202,
                response_body=response_body,
            )

            # Step F: Commit all entities atomically before returning HTTP 202
            await session.commit()

            return IngestionResult(
                status_code=202,
                event_id=event.id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                is_replay=False,
                response_body=response_body,
                response_headers={},
            )

        except (IntegrityError, DBAPIError) as exc:
            # Trapped uniqueness conflict on idx_idempotency_project_key_active
            logger.warning(
                "Integrity conflict on key %s for project %s: %s; initiating recovery",
                idempotency_key,
                project_id,
                exc,
            )
            await session.rollback()
            return await self._handle_concurrency_conflict(
                session=session,
                project_id=project_id,
                idempotency_key=idempotency_key,
                event_type=event_type,
                raw_payload_bytes=raw_payload_bytes,
                incoming_fingerprint=fingerprint,
                retention_days=retention_days,
            )

    def _evaluate_active_key(
        self,
        active_key: IdempotencyKey,
        idempotency_key: str,
        incoming_fingerprint: str,
    ) -> IngestionResult:
        """Evaluate an existing active key against incoming fingerprint."""
        if active_key.fingerprint == incoming_fingerprint:
            # Idempotent duplicate replay: return original acceptance body
            resp_body = active_key.response_body or {
                "event_id": str(active_key.event_id or active_key.id),
                "status": "accepted",
                "idempotency_key": idempotency_key,
                "fingerprint": active_key.fingerprint,
                "created_at": active_key.created_at.isoformat(),
            }
            return IngestionResult(
                status_code=200,
                event_id=active_key.event_id or active_key.id,
                idempotency_key=idempotency_key,
                fingerprint=active_key.fingerprint,
                is_replay=True,
                response_body=resp_body,
                response_headers={"Idempotent-Replay": "true"},
            )
        else:
            # Fingerprint mismatch: return HTTP 409
            raise IdempotencyFingerprintMismatchError(
                f"Idempotency key '{idempotency_key}' already exists with a different fingerprint."
            )

    async def _handle_concurrency_conflict(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        idempotency_key: str,
        event_type: str,
        raw_payload_bytes: bytes,
        incoming_fingerprint: str,
        retention_days: int | None = None,
    ) -> IngestionResult:
        """Recover from a uniqueness conflict by opening a clean transaction and re-reading."""
        bind = cast(AsyncEngine | AsyncConnection, session.get_bind())
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=bind,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        for _ in range(20):
            async with factory() as fresh_session:
                repo = IdempotencyKeyRepository(fresh_session)
                active_key = await repo.get_active(project_id, idempotency_key)

                if active_key is not None:
                    if active_key.response_body is not None:
                        return self._evaluate_active_key(
                            active_key=active_key,
                            idempotency_key=idempotency_key,
                            incoming_fingerprint=incoming_fingerprint,
                        )
                    await asyncio.sleep(0.02)
                    continue

            await asyncio.sleep(0.02)

        # Fallback / retry fresh ingestion if no active key exists
        async with factory() as fallback_session:
            repo = IdempotencyKeyRepository(fallback_session)
            active_key = await repo.get_active(project_id, idempotency_key)
            if active_key is not None:
                return self._evaluate_active_key(
                    active_key=active_key,
                    idempotency_key=idempotency_key,
                    incoming_fingerprint=incoming_fingerprint,
                )
            return await self.process_ingestion(
                session=fallback_session,
                project_id=project_id,
                idempotency_key=idempotency_key,
                event_type=event_type,
                raw_payload_bytes=raw_payload_bytes,
                fingerprint=incoming_fingerprint,
                retention_days=retention_days,
            )


idempotency_service = IdempotencyService()
