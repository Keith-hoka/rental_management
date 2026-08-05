"""add jurisdiction to audit tables

Revision ID: b2529b7f437c
Revises: b7d31f8c4e21
Create Date: 2026-08-05 19:31:53.470086

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2529b7f437c"
down_revision: str | Sequence[str] | None = "b7d31f8c4e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add jurisdiction to lease_audits and lease_clause_audits, defaulting to NSW."""
    op.add_column(
        "lease_audits",
        sa.Column("jurisdiction", sa.String(length=3), server_default="NSW", nullable=False),
    )
    op.add_column(
        "lease_clause_audits",
        sa.Column("jurisdiction", sa.String(length=3), server_default="NSW", nullable=False),
    )


def downgrade() -> None:
    """Drop jurisdiction from lease_audits and lease_clause_audits."""
    op.drop_column("lease_clause_audits", "jurisdiction")
    op.drop_column("lease_audits", "jurisdiction")
