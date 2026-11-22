"""M1 Gate 3 schema migration: idempotency_keys, events, deliveries, outbox.

Revision ID: 0002_m1_gate3_schema
Revises: 0001_initial_baseline
Create Date: 2026-11-22

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "0002_m1_gate3_schema"
down_revision: Union[str, None] = "0001_initial_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create M1 Gate 3 persistence tables, constraints, and indexes."""
    # 1. Create idempotency_keys table (without deferred FK to events yet)
    op.create_table(
        "idempotency_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_headers", JSONB, nullable=True),
        sa.Column("response_body", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_idempotency_keys_project_id",
        "idempotency_keys",
        ["project_id"],
    )
    # Partial unique index (HR-IDEM-002)
    op.create_index(
        "idx_idempotency_project_key_active",
        "idempotency_keys",
        ["project_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )

    # 2. Create events table
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("raw_payload_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["idempotency_key_id"],
            ["idempotency_keys.id"],
            name="fk_events_idempotency_key",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_events_project_id", "events", ["project_id"])

    # 3. Add deferred foreign key from idempotency_keys.event_id to events.id (HR-ARCH-001)
    op.create_foreign_key(
        "fk_idempotency_keys_event_id",
        "idempotency_keys",
        "events",
        ["event_id"],
        ["id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )

    # 4. Create deliveries table
    op.create_table(
        "deliveries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_deliveries_event_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_deliveries_project_id", "deliveries", ["project_id"])
    op.create_index("ix_deliveries_event_id", "deliveries", ["event_id"])
    op.create_index("ix_deliveries_status", "deliveries", ["status"])

    # 5. Create outbox table
    op.create_table(
        "outbox",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_outbox_event_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_outbox_event_id", "outbox", ["event_id"])
    op.create_index("ix_outbox_status", "outbox", ["status"])


def downgrade() -> None:
    """Drop M1 Gate 3 persistence tables, constraints, and indexes."""
    # Drop in reverse order
    op.drop_table("outbox")
    op.drop_table("deliveries")
    # Drop deferred FK before dropping events
    op.drop_constraint("fk_idempotency_keys_event_id", "idempotency_keys", type_="foreignkey")
    op.drop_table("events")
    op.drop_table("idempotency_keys")
