"""Integration tests for Outbox and Delivery architecture (M1 Gate 3)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import Delivery, Event, IdempotencyKey, Outbox
from app.repositories.delivery import DeliveryRepository
from app.repositories.outbox import OutboxRepository
from app.services.idempotency import IdempotencyService
from app.services.outbox import OutboxDispatcherService


@pytest.mark.asyncio
async def test_outbox_repository_lifecycle(db_session: AsyncSession) -> None:
    """Verify OutboxRepository creation, retrieval, dispatch marking, and deletion."""
    repo = OutboxRepository(db_session)
    project_id = uuid.uuid4()
    key_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Setup parent IdempotencyKey and Event
    key = IdempotencyKey(
        id=key_id,
        project_id=project_id,
        idempotency_key="key_outbox_repo",
        fingerprint="jcs-rfc8785-v1:" + "a" * 64,
        created_at=now,
        expires_at=now,
    )
    db_session.add(key)
    await db_session.flush()

    event = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=key.id,
        event_type="test.event",
        raw_payload_bytes=b'{"k": "v"}',
        payload_hash=key.fingerprint,
        created_at=now,
    )
    db_session.add(event)
    await db_session.flush()

    # 1. Create Outbox entry
    outbox = await repo.create(
        event_id=event.id,
        payload={"event_id": str(event.id), "event_type": "test.event"},
        status="pending",
        created_at=now,
    )
    assert outbox.id is not None
    assert outbox.status == "pending"

    # 2. Get by event_id
    records = await repo.get_by_event_id(event.id)
    assert len(records) == 1
    assert records[0].id == outbox.id

    # 3. Get pending
    pending = await repo.get_pending(limit=10)
    assert any(p.id == outbox.id for p in pending)

    # 4. Mark dispatched
    dispatched = await repo.mark_dispatched(outbox.id, processed_at=now)
    assert dispatched is True

    # 5. Verify status updated
    updated_records = await repo.get_by_event_id(event.id)
    assert updated_records[0].status == "dispatched"
    assert updated_records[0].processed_at is not None

    # 6. Delete by event_id
    deleted_count = await repo.delete_by_event_ids([event.id])
    assert deleted_count == 1
    remaining = await repo.get_by_event_id(event.id)
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_delivery_repository_lifecycle(db_session: AsyncSession) -> None:
    """Verify DeliveryRepository creation, retrieval, status update, and deletion."""
    repo = DeliveryRepository(db_session)
    project_id = uuid.uuid4()
    key_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Setup parent IdempotencyKey and Event
    key = IdempotencyKey(
        id=key_id,
        project_id=project_id,
        idempotency_key="key_delivery_repo",
        fingerprint="jcs-rfc8785-v1:" + "b" * 64,
        created_at=now,
        expires_at=now,
    )
    db_session.add(key)
    await db_session.flush()

    event = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=key.id,
        event_type="delivery.event",
        raw_payload_bytes=b'{"deliv": true}',
        payload_hash=key.fingerprint,
        created_at=now,
    )
    db_session.add(event)
    await db_session.flush()

    # 1. Create Delivery
    delivery = await repo.create(
        project_id=project_id,
        event_id=event.id,
        status="pending",
        created_at=now,
    )
    assert delivery.status == "pending"
    assert delivery.attempt_count == 0

    # 2. Get by event_id
    records = await repo.get_by_event_id(event.id)
    assert len(records) == 1
    assert records[0].id == delivery.id

    # 3. Get pending by project
    pending = await repo.get_pending_by_project(project_id)
    assert any(p.id == delivery.id for p in pending)

    # 4. Update status and attempts
    await repo.update_status(
        delivery_id=delivery.id,
        status="delivered",
        next_attempt_at=now,
    )

    # 5. Verify update
    updated_records = await repo.get_by_event_id(event.id)
    assert updated_records[0].status == "delivered"
    assert updated_records[0].attempt_count == 1

    # 6. Delete by event_ids
    deleted = await repo.delete_by_event_ids([event.id])
    assert deleted == 1


@pytest.mark.asyncio
async def test_outbox_dispatcher_batch_signals_and_marks_dispatched(
    db_session: AsyncSession,
) -> None:
    """Verify OutboxDispatcherService signals Redis and marks pending outbox records dispatched."""
    project_id = uuid.uuid4()
    key_id = uuid.uuid4()
    now = datetime.now(UTC)

    key = IdempotencyKey(
        id=key_id,
        project_id=project_id,
        idempotency_key="key_dispatcher",
        fingerprint="jcs-rfc8785-v1:" + "c" * 64,
        created_at=now,
        expires_at=now,
    )
    db_session.add(key)
    await db_session.flush()

    event = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=key.id,
        event_type="outbox.dispatch.test",
        raw_payload_bytes=b"{}",
        payload_hash=key.fingerprint,
        created_at=now,
    )
    db_session.add(event)
    await db_session.flush()

    outbox_repo = OutboxRepository(db_session)
    await outbox_repo.create(
        event_id=event.id,
        payload={
            "event_id": str(event.id),
            "project_id": str(project_id),
            "event_type": "outbox.dispatch.test",
        },
        status="pending",
        created_at=now,
    )
    await db_session.commit()

    # Mock Redis client returning success
    mock_redis = AsyncMock()
    mock_redis.signal_outbox_event.return_value = True

    dispatcher = OutboxDispatcherService(redis_override=mock_redis)
    dispatched_count = await dispatcher.dispatch_pending_batch(db_session, limit=10)

    assert dispatched_count == 1
    mock_redis.signal_outbox_event.assert_awaited_once_with(
        event_id=str(event.id),
        project_id=str(project_id),
        event_type="outbox.dispatch.test",
    )

    # Check updated status
    records = await outbox_repo.get_by_event_id(event.id)
    assert records[0].status == "dispatched"


@pytest.mark.asyncio
async def test_idempotency_service_signals_redis_after_commit(
    db_session: AsyncSession,
) -> None:
    """Verify IdempotencyService signals Redis after successful commit."""
    mock_redis = AsyncMock()
    mock_redis.signal_outbox_event.return_value = True

    service = IdempotencyService(redis_client_override=mock_redis)
    project_id = uuid.uuid4()
    key = "key_redis_signal_" + uuid.uuid4().hex[:8]

    result = await service.process_ingestion(
        session=db_session,
        project_id=project_id,
        idempotency_key=key,
        event_type="order.placed",
        raw_payload_bytes=b'{"order_id": 1}',
        fingerprint="jcs-rfc8785-v1:" + "d" * 64,
    )

    assert result.status_code == 202
    mock_redis.signal_outbox_event.assert_awaited_once_with(
        event_id=result.event_id,
        project_id=project_id,
        event_type="order.placed",
    )


@pytest.mark.asyncio
async def test_idempotency_service_redis_failure_does_not_abort_202(
    db_session: AsyncSession,
) -> None:
    """Verify that a Redis error during post-commit signaling does NOT abort the 202 response.

    Event, Delivery, and Outbox remain committed in PostgreSQL (durable source of truth).
    """
    mock_redis = AsyncMock()
    mock_redis.signal_outbox_event.side_effect = ConnectionError("Redis cluster unreachable")

    service = IdempotencyService(redis_client_override=mock_redis)
    project_id = uuid.uuid4()
    key = "key_redis_fail_" + uuid.uuid4().hex[:8]

    result = await service.process_ingestion(
        session=db_session,
        project_id=project_id,
        idempotency_key=key,
        event_type="invoice.generated",
        raw_payload_bytes=b'{"invoice_id": 999}',
        fingerprint="jcs-rfc8785-v1:" + "e" * 64,
    )

    # 202 is still returned
    assert result.status_code == 202
    assert result.event_id is not None

    # Verify all records exist in DB
    event_res = await db_session.execute(select(Event).where(Event.id == result.event_id))
    assert event_res.scalar_one_or_none() is not None

    outbox_res = await db_session.execute(select(Outbox).where(Outbox.event_id == result.event_id))
    assert outbox_res.scalar_one_or_none() is not None

    deliv_res = await db_session.execute(
        select(Delivery).where(Delivery.event_id == result.event_id)
    )
    assert deliv_res.scalar_one_or_none() is not None
