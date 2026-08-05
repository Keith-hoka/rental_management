"""drop jurisdiction server defaults

Revision ID: 00cbeeefeadc
Revises: b2529b7f437c
Create Date: 2026-08-06 01:45:14.092234

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "00cbeeefeadc"
down_revision: str | Sequence[str] | None = "b2529b7f437c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the NSW server default; the historical backfill is done.

    NOT NULL stays, so a construction site that forgets jurisdiction fails
    loudly instead of silently becoming NSW.
    """
    op.alter_column(
        "lease_audits",
        "jurisdiction",
        server_default=None,
        existing_type=sa.String(length=3),
        existing_nullable=False,
    )
    op.alter_column(
        "lease_clause_audits",
        "jurisdiction",
        server_default=None,
        existing_type=sa.String(length=3),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Restore the NSW server default on both audit tables."""
    op.alter_column(
        "lease_clause_audits",
        "jurisdiction",
        server_default="NSW",
        existing_type=sa.String(length=3),
        existing_nullable=False,
    )
    op.alter_column(
        "lease_audits",
        "jurisdiction",
        server_default="NSW",
        existing_type=sa.String(length=3),
        existing_nullable=False,
    )
