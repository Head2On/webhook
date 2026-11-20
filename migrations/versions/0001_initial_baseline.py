"""Initial baseline migration for M0 foundation verification.

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create M0 baseline marker table to verify migration execution."""
    op.create_table(
        "_m0_baseline_marker",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
    )


def downgrade() -> None:
    """Drop M0 baseline marker table."""
    op.drop_table("_m0_baseline_marker")
