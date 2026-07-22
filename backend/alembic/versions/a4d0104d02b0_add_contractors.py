"""add contractors

Revision ID: a4d0104d02b0
Revises: 0e4536ea7e9a
Create Date: 2026-07-23 01:54:25.732261

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4d0104d02b0"
down_revision: Union[str, Sequence[str], None] = "0e4536ea7e9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contractors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("trade", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contractors_organization_id", "contractors", ["organization_id"])
    op.add_column("maintenance_requests", sa.Column("contractor_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_maintenance_requests_contractor_id_contractors",
        "maintenance_requests",
        "contractors",
        ["contractor_id"],
        ["id"],
    )
    op.create_index(
        "ix_maintenance_requests_contractor_id", "maintenance_requests", ["contractor_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    # The column goes before the table: the FK points from maintenance_requests
    # to contractors, so dropping the table first would fail.
    op.drop_index("ix_maintenance_requests_contractor_id", table_name="maintenance_requests")
    op.drop_constraint(
        "fk_maintenance_requests_contractor_id_contractors",
        "maintenance_requests",
        type_="foreignkey",
    )
    op.drop_column("maintenance_requests", "contractor_id")
    op.drop_index("ix_contractors_organization_id", table_name="contractors")
    op.drop_table("contractors")
