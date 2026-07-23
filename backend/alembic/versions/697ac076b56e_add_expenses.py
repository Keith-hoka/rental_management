"""add expenses

Revision ID: 697ac076b56e
Revises: 551fe4865e44
Create Date: 2026-07-24 04:15:55.814672

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "697ac076b56e"
down_revision: Union[str, Sequence[str], None] = "551fe4865e44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "maintenance",
                "insurance",
                "tax",
                "utilities",
                "management",
                "other",
                name="expensecategory",
            ),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("property_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_expenses_organization_id"), "expenses", ["organization_id"])
    op.create_index(op.f("ix_expenses_property_id"), "expenses", ["property_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_expenses_property_id"), table_name="expenses")
    op.drop_index(op.f("ix_expenses_organization_id"), table_name="expenses")
    op.drop_table("expenses")
    sa.Enum(name="expensecategory").drop(op.get_bind())
