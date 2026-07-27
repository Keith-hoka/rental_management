"""add compliance tables

Revision ID: 464c768e8a2b
Revises: 4abe524e31f2
Create Date: 2026-07-27 21:51:39.636851

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "464c768e8a2b"
down_revision: str | Sequence[str] | None = "4abe524e31f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create lease_audits, compliance_audit_queue and compliance_sync_state."""
    op.create_table(
        "lease_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lease_id", sa.Uuid(), sa.ForeignKey("leases.id"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("as_at", sa.Date(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_lease_audits_lease_id", "lease_audits", ["lease_id"])
    op.create_index("ix_lease_audits_organization_id", "lease_audits", ["organization_id"])

    op.create_table(
        "compliance_audit_queue",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lease_id", sa.Uuid(), sa.ForeignKey("leases.id"), nullable=False, unique=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "compliance_sync_state",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("value", sa.String(100), nullable=False),
    )


def downgrade() -> None:
    """Drop the three compliance tables."""
    op.drop_table("compliance_sync_state")
    op.drop_table("compliance_audit_queue")
    op.drop_index("ix_lease_audits_organization_id", "lease_audits")
    op.drop_index("ix_lease_audits_lease_id", "lease_audits")
    op.drop_table("lease_audits")
