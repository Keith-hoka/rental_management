"""add calendar_events

Revision ID: 551fe4865e44
Revises: 591d2d4c3249
Create Date: 2026-07-23 16:23:52.572007

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "551fe4865e44"
down_revision: Union[str, Sequence[str], None] = "591d2d4c3249"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_calendar_events_organization_id"), "calendar_events", ["organization_id"]
    )
    op.create_index(op.f("ix_calendar_events_property_id"), "calendar_events", ["property_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_calendar_events_property_id"), table_name="calendar_events")
    op.drop_index(op.f("ix_calendar_events_organization_id"), table_name="calendar_events")
    op.drop_table("calendar_events")
