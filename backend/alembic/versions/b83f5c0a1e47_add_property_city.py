"""add property city

Revision ID: b83f5c0a1e47
Revises: 7c1a4b9e2d05
Create Date: 2026-07-22

"""

import sqlalchemy as sa
from alembic import op

revision = "b83f5c0a1e47"
down_revision = "7c1a4b9e2d05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("city", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("properties", "city")
