"""Integration tests for Webhook Ingestion API (M1 Gate 3)."""

import json
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_webhook_success_returns_202(async_client: AsyncClient) -> None:
    """Verify fresh webhook ingestion returns HTTP 202 and creates durable records."""
    project_id = uuid.uuid4()
    headers = {
        "Idempotency-Key": "key_ingest_202_" + uuid.uuid4().hex[:8],
        "X-Event-Type": "order.created",
        "Content-Type": "application/json",
    }
    payload = {"order_id": 12345, "amount": 99.99, "currency": "USD"}

    response = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=json.dumps(payload),
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["idempotency_key"] == headers["Idempotency-Key"]
    assert "event_id" in data
    assert "fingerprint" in data
    assert data["fingerprint"].startswith("jcs-rfc8785-v1:")
    assert "Idempotent-Replay" not in response.headers


@pytest.mark.asyncio
async def test_post_webhook_duplicate_identical_returns_200(async_client: AsyncClient) -> None:
    """Verify duplicate submission with identical payload returns HTTP 200 with replay header."""
    project_id = uuid.uuid4()
    headers = {
        "Idempotency-Key": "key_replay_200_" + uuid.uuid4().hex[:8],
        "X-Event-Type": "user.signup",
        "Content-Type": "application/json",
    }
    payload = {"user_id": "usr_99", "email": "test@example.com"}

    # 1. Initial submission
    res_1 = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=json.dumps(payload),
    )
    assert res_1.status_code == 202
    body_1 = res_1.json()

    # 2. Duplicate submission
    res_2 = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=json.dumps(payload),
    )
    assert res_2.status_code == 200
    assert res_2.headers.get("Idempotent-Replay") == "true"
    assert res_2.json() == body_1


@pytest.mark.asyncio
async def test_post_webhook_duplicate_different_payload_returns_409(
    async_client: AsyncClient,
) -> None:
    """Verify key reuse with modified payload returns HTTP 409 Conflict."""
    project_id = uuid.uuid4()
    key = "key_conflict_409_" + uuid.uuid4().hex[:8]
    headers = {
        "Idempotency-Key": key,
        "X-Event-Type": "test.event",
        "Content-Type": "application/json",
    }

    # 1. Initial submission
    res_1 = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=json.dumps({"version": 1}),
    )
    assert res_1.status_code == 202

    # 2. Conflicting submission
    res_2 = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=json.dumps({"version": 2}),
    )
    assert res_2.status_code == 409
    data = res_2.json()
    assert data["error"] == "IDEMPOTENCY_KEY_FINGERPRINT_MISMATCH"


@pytest.mark.asyncio
async def test_post_webhook_depth_33_returns_400(async_client: AsyncClient) -> None:
    """Verify depth 33 nesting rejection returns HTTP 400 per HR-IDEM-002."""
    project_id = uuid.uuid4()
    headers = {
        "Idempotency-Key": "depth_33_" + uuid.uuid4().hex[:8],
        "Content-Type": "application/json",
    }
    # Build depth 33 object: {"a": {"a": ... 33 times ... 1}}}
    obj_str = '{"a":' * 33 + "1" + "}" * 33

    response = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=obj_str,
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "PAYLOAD_NESTING_DEPTH_EXCEEDED"


@pytest.mark.asyncio
async def test_post_webhook_unsafe_integer_returns_400(async_client: AsyncClient) -> None:
    """Verify integer outside safe range [-(2^53-1), 2^53-1] returns HTTP 400."""
    project_id = uuid.uuid4()
    headers = {
        "Idempotency-Key": "unsafe_int_" + uuid.uuid4().hex[:8],
        "Content-Type": "application/json",
    }
    # 2^53 = 9007199254740992
    payload_str = '{"unsafe_int": 9007199254740992}'

    response = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=payload_str,
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "UNSAFE_INTEGER_RANGE_EXCEEDED"


@pytest.mark.asyncio
async def test_post_webhook_non_object_root_returns_400(async_client: AsyncClient) -> None:
    """Verify non-object root (e.g. array) returns HTTP 400 per REQ-INGEST-01."""
    project_id = uuid.uuid4()
    headers = {
        "Idempotency-Key": "array_root_" + uuid.uuid4().hex[:8],
        "Content-Type": "application/json",
    }

    response = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content="[1, 2, 3]",
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "TOP_LEVEL_OBJECT_REQUIRED"


@pytest.mark.asyncio
async def test_post_webhook_duplicate_key_returns_400(async_client: AsyncClient) -> None:
    """Verify duplicate key rejection returns HTTP 400 per REQ-INGEST-02."""
    project_id = uuid.uuid4()
    headers = {
        "Idempotency-Key": "dup_key_" + uuid.uuid4().hex[:8],
        "Content-Type": "application/json",
    }
    payload_str = '{"k": 1, "k": 2}'

    response = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=payload_str,
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "DUPLICATE_OBJECT_KEY"


@pytest.mark.asyncio
async def test_post_webhook_payload_exceeding_1mib_returns_413(
    async_client: AsyncClient,
) -> None:
    """Verify payload exceeding 1 MiB (1,048,576 bytes) returns HTTP 413 Payload Too Large."""
    project_id = uuid.uuid4()
    headers = {
        "Idempotency-Key": "too_large_" + uuid.uuid4().hex[:8],
        "Content-Type": "application/json",
    }
    # Create payload exactly 1,048,577 bytes: {"data":"..."}
    prefix = '{"data":"'
    suffix = '"}'
    padding_len = 1_048_577 - len(prefix) - len(suffix)
    oversized_payload = prefix + ("x" * padding_len) + suffix
    assert len(oversized_payload.encode("utf-8")) == 1_048_577

    response = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=headers,
        content=oversized_payload,
    )
    assert response.status_code == 413
    data = response.json()
    assert data["error"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_post_webhook_unsupported_media_type_returns_415(
    async_client: AsyncClient,
) -> None:
    """Verify non-application/json content type or compressed encoding returns HTTP 415."""
    project_id = uuid.uuid4()

    # 1. Non-JSON Content-Type
    res_1 = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers={
            "Idempotency-Key": "ct_test_" + uuid.uuid4().hex[:8],
            "Content-Type": "text/plain",
        },
        content="plain text",
    )
    assert res_1.status_code == 415
    assert res_1.json()["error"] == "UNSUPPORTED_MEDIA_TYPE"

    # 2. Unsupported Content-Encoding
    res_2 = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers={
            "Idempotency-Key": "ce_test_" + uuid.uuid4().hex[:8],
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
        content='{"gzip": true}',
    )
    assert res_2.status_code == 415
    assert res_2.json()["error"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.asyncio
async def test_post_webhook_missing_idempotency_key_returns_400(
    async_client: AsyncClient,
) -> None:
    """Verify missing Idempotency-Key header returns HTTP 400 Bad Request."""
    project_id = uuid.uuid4()
    response = await async_client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers={"Content-Type": "application/json"},
        content='{"valid": "json"}',
    )
    assert response.status_code == 400
    assert response.json()["error"] == "IDEMPOTENCY_KEY_REQUIRED"
