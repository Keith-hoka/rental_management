"""add lease money fields

Revision ID: a96ec8fc1f5c
Revises: e013b774ee2a
Create Date: 2026-07-28 01:39:38.403483

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a96ec8fc1f5c"
down_revision: str | Sequence[str] | None = "e013b774ee2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the four compliance money columns to leases."""
    op.add_column("leases", sa.Column("rent_in_advance_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("leases", sa.Column("holding_deposit_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("leases", sa.Column("other_security_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("leases", sa.Column("break_fee_amount", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    """Drop the four compliance money columns."""
    op.drop_column("leases", "break_fee_amount")
    op.drop_column("leases", "other_security_amount")
    op.drop_column("leases", "holding_deposit_amount")
    op.drop_column("leases", "rent_in_advance_amount")
