"""cascade compliance lease fks

Revision ID: e013b774ee2a
Revises: 464c768e8a2b
Create Date: 2026-07-27 23:46:06.933349

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e013b774ee2a"
down_revision: str | Sequence[str] | None = "464c768e8a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Recreate the compliance lease FKs with ON DELETE CASCADE."""
    op.drop_constraint("lease_audits_lease_id_fkey", "lease_audits", type_="foreignkey")
    op.create_foreign_key(
        "lease_audits_lease_id_fkey",
        "lease_audits",
        "leases",
        ["lease_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "compliance_audit_queue_lease_id_fkey", "compliance_audit_queue", type_="foreignkey"
    )
    op.create_foreign_key(
        "compliance_audit_queue_lease_id_fkey",
        "compliance_audit_queue",
        "leases",
        ["lease_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Restore the FKs without cascade."""
    op.drop_constraint(
        "compliance_audit_queue_lease_id_fkey", "compliance_audit_queue", type_="foreignkey"
    )
    op.create_foreign_key(
        "compliance_audit_queue_lease_id_fkey",
        "compliance_audit_queue",
        "leases",
        ["lease_id"],
        ["id"],
    )
    op.drop_constraint("lease_audits_lease_id_fkey", "lease_audits", type_="foreignkey")
    op.create_foreign_key(
        "lease_audits_lease_id_fkey",
        "lease_audits",
        "leases",
        ["lease_id"],
        ["id"],
    )
