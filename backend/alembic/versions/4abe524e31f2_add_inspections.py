"""add inspections

Revision ID: 4abe524e31f2
Revises: 697ac076b56e
Create Date: 2026-07-24 14:04:13.123574

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4abe524e31f2"
down_revision: Union[str, Sequence[str], None] = "697ac076b56e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inspections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column(
            "type",
            sa.Enum("move_in", "move_out", "routine", name="inspectiontype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("scheduled", "completed", name="inspectionstatus"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("image_urls", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_inspections_organization_id"), "inspections", ["organization_id"])
    op.create_index(op.f("ix_inspections_property_id"), "inspections", ["property_id"])
    op.create_index(op.f("ix_inspections_lease_id"), "inspections", ["lease_id"])
    op.create_table(
        "inspection_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("area", sa.String(length=100), nullable=False),
        sa.Column(
            "condition",
            sa.Enum("good", "fair", "poor", name="inspectioncondition"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inspection_items_inspection_id"),
        "inspection_items",
        ["inspection_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_inspection_items_inspection_id"), table_name="inspection_items")
    op.drop_table("inspection_items")
    op.drop_index(op.f("ix_inspections_lease_id"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_property_id"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_organization_id"), table_name="inspections")
    op.drop_table("inspections")
    sa.Enum(name="inspectioncondition").drop(op.get_bind())
    sa.Enum(name="inspectiontype").drop(op.get_bind())
    sa.Enum(name="inspectionstatus").drop(op.get_bind())
