"""Webhook ingestion API endpoint implementing M1 Gate 3 contract."""

from __future__ import annotations

import json
import uuid

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.db.session import get_db_session
from app.services.canonicalizer import canonicalize
from app.services.idempotency import idempotency_service

router = APIRouter(tags=["webhooks"])
settings = get_settings()


async def read_streaming_payload(request: Request, max_size_bytes: int) -> bytes:
    """Stream request body chunks with strict size and framing enforcement."""
    # Check Content-Encoding
    content_encoding = request.headers.get("content-encoding")
    if content_encoding and content_encoding.lower() not in ("identity", ""):
        raise UnsupportedMediaTypeError("Compression algorithms are not supported.")

    # Check Content-Type
    content_type = request.headers.get("content-type", "")
    if content_type:
        base_type = content_type.split(";")[0].strip().lower()
        if base_type != "application/json":
            raise UnsupportedMediaTypeError(
                f"Content-Type '{content_type}' is unsupported. Must be 'application/json'."
            )

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_size_bytes:
            raise PayloadTooLargeError(
                f"Payload size {len(body)} exceeds maximum allowed limit of {max_size_bytes} bytes."
            )
    return bytes(body)


@router.post("/projects/{project_id}/webhooks", status_code=status.HTTP_202_ACCEPTED)
@router.post("/webhooks", status_code=status.HTTP_202_ACCEPTED)
async def ingest_webhook(
    request: Request,
    project_id: uuid.UUID | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_event_type: str | None = Header(default=None, alias="X-Event-Type"),
    x_project_id: uuid.UUID | None = Header(default=None, alias="X-Project-Id"),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Ingest webhook payload with RFC 8785 canonicalization and transactional idempotency."""
    effective_project_id = project_id or x_project_id
    if effective_project_id is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "PROJECT_ID_REQUIRED",
                "message": "project_id is required in URL path or X-Project-Id header.",
            },
        )

    if not idempotency_key or not idempotency_key.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "IDEMPOTENCY_KEY_REQUIRED",
                "message": "Idempotency-Key header is required.",
            },
        )

    # 1. Read and enforce streaming payload limit (1 MiB)
    raw_payload_bytes = await read_streaming_payload(request, settings.MAX_PAYLOAD_SIZE_BYTES)
    if not raw_payload_bytes:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "PAYLOAD_EMPTY", "message": "Payload body cannot be empty."},
        )

    # 2. Canonicalize and compute SHA-256 fingerprint
    _canonical_bytes, fingerprint = canonicalize(raw_payload_bytes)

    # 3. Process durable ingestion & idempotency transaction
    event_type = x_event_type or "webhook.received"
    result = await idempotency_service.process_ingestion(
        session=session,
        project_id=effective_project_id,
        idempotency_key=idempotency_key.strip(),
        event_type=event_type,
        raw_payload_bytes=raw_payload_bytes,
        fingerprint=fingerprint,
    )

    headers = {"Content-Type": "application/json"}
    headers.update(result.response_headers)

    return Response(
        content=json.dumps(result.response_body),
        status_code=result.status_code,
        headers=headers,
        media_type="application/json",
    )
