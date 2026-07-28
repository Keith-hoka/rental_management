"""lease_clause_audits

Revision ID: b7d31f8c4e21
Revises: a96ec8fc1f5c
Create Date: 2026-07-28

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d31f8c4e21"
down_revision: str | Sequence[str] | None = "a96ec8fc1f5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the lease_clause_audits table."""
    op.create_table(
        "lease_clause_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "lease_id",
            sa.Uuid(),
            sa.ForeignKey("leases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.Uuid(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_id", sa.String(36), nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("discrepancies", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("engine_version", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_lease_clause_audits_organization_id", "lease_clause_audits", ["organization_id"]
    )
    op.create_index("ix_lease_clause_audits_lease_id", "lease_clause_audits", ["lease_id"])
    op.create_index("ix_lease_clause_audits_document_id", "lease_clause_audits", ["document_id"])


def downgrade() -> None:
    """Drop the lease_clause_audits table."""
    op.drop_index("ix_lease_clause_audits_document_id", "lease_clause_audits")
    op.drop_index("ix_lease_clause_audits_lease_id", "lease_clause_audits")
    op.drop_index("ix_lease_clause_audits_organization_id", "lease_clause_audits")
    op.drop_table("lease_clause_audits")
