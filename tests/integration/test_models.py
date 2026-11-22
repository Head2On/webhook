"""Integration tests for M1 Gate 3 database models and relational constraints."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Delivery, Event, IdempotencyKey, Outbox


@pytest.mark.asyncio
async def test_deferred_foreign_key_and_event_persistence(db_session: AsyncSession) -> None:
    """Verify DEFERRABLE INITIALLY DEFERRED FK allows inserting key before event in transaction."""
    project_id = uuid.uuid4()
    now = datetime.now(UTC)

    # 1. Insert idempotency key claim without event_id
    key_record = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="test_deferred_key_1",
        fingerprint="jcs-rfc8785-v1:" + "a" * 64,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(key_record)
    await db_session.flush()

    # 2. Insert event referencing the idempotency key
    raw_payload = b'{"msg":"hello world \xe2\x9c\xa8"}'
    event_record = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=key_record.id,
        event_type="test.event",
        raw_payload_bytes=raw_payload,
        payload_hash=key_record.fingerprint,
        created_at=now,
    )
    db_session.add(event_record)
    await db_session.flush()

    # 3. Associate event with idempotency key
    key_record.event_id = event_record.id
    key_record.response_status_code = 202
    key_record.response_body = {"status": "accepted", "event_id": str(event_record.id)}
    await db_session.flush()

    # 4. Verify Event raw payload fidelity
    query = select(Event).where(Event.id == event_record.id)
    result = await db_session.execute(query)
    fetched_event = result.scalar_one()
    assert fetched_event.raw_payload_bytes == raw_payload
    assert fetched_event.event_type == "test.event"


@pytest.mark.asyncio
async def test_partial_unique_index_active_key_uniqueness(db_session: AsyncSession) -> None:
    """Verify partial unique index prevents two active keys with the same project and key string."""
    project_id = uuid.uuid4()
    now = datetime.now(UTC)

    key_1 = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="unique_key_test",
        fingerprint="jcs-rfc8785-v1:" + "1" * 64,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(key_1)
    await db_session.flush()

    # Second active key with identical project_id and key string must fail partial unique index
    key_2 = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="unique_key_test",
        fingerprint="jcs-rfc8785-v1:" + "2" * 64,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(key_2)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_retired_key_allows_immediate_key_reuse(db_session: AsyncSession) -> None:
    """Verify that once a key has retired_at set, the same key string can be inserted."""
    project_id = uuid.uuid4()
    now = datetime.now(UTC)

    # 1. Active key
    key_1 = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="reused_key_test",
        fingerprint="jcs-rfc8785-v1:" + "1" * 64,
        created_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=3),
        retired_at=now,  # Marked as retired
    )
    db_session.add(key_1)
    await db_session.flush()

    # 2. Fresh replacement active key with the same idempotency_key must succeed
    key_2 = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="reused_key_test",
        fingerprint="jcs-rfc8785-v1:" + "2" * 64,
        created_at=now,
        expires_at=now + timedelta(days=7),
        retired_at=None,
    )
    db_session.add(key_2)
    await db_session.flush()

    # Query both
    query = (
        select(IdempotencyKey)
        .where(
            IdempotencyKey.project_id == project_id,
            IdempotencyKey.idempotency_key == "reused_key_test",
        )
        .order_by(IdempotencyKey.created_at)
    )
    result = await db_session.execute(query)
    records = result.scalars().all()
    assert len(records) == 2
    assert records[0].retired_at is not None
    assert records[1].retired_at is None


@pytest.mark.asyncio
async def test_delivery_and_outbox_persistence(db_session: AsyncSession) -> None:
    """Verify Delivery and Outbox records are durably persisted and linked to Event."""
    project_id = uuid.uuid4()
    now = datetime.now(UTC)

    key_record = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="delivery_outbox_key",
        fingerprint="jcs-rfc8785-v1:" + "d" * 64,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(key_record)
    await db_session.flush()

    event = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=key_record.id,
        event_type="order.completed",
        raw_payload_bytes=b'{"order_id": 999}',
        payload_hash=key_record.fingerprint,
        created_at=now,
    )
    db_session.add(event)
    await db_session.flush()

    # Create Delivery
    delivery = Delivery(
        id=uuid.uuid4(),
        project_id=project_id,
        event_id=event.id,
        status="pending",
        attempt_count=0,
    )
    db_session.add(delivery)

    # Create Outbox
    outbox = Outbox(
        id=uuid.uuid4(),
        event_id=event.id,
        status="pending",
        payload={"event_id": str(event.id), "event_type": "order.completed"},
    )
    db_session.add(outbox)
    await db_session.flush()

    # Query back
    deliv_res = await db_session.execute(select(Delivery).where(Delivery.event_id == event.id))
    fetched_delivery = deliv_res.scalar_one()
    assert fetched_delivery.status == "pending"
    assert fetched_delivery.attempt_count == 0

    outbox_res = await db_session.execute(select(Outbox).where(Outbox.event_id == event.id))
    fetched_outbox = outbox_res.scalar_one()
    assert fetched_outbox.status == "pending"
    assert fetched_outbox.payload == {"event_id": str(event.id), "event_type": "order.completed"}
