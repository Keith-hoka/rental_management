"""add property state and postcode

Revision ID: 7c1a4b9e2d05
Revises: 59285cbffe1c
Create Date: 2026-07-22

"""

import sqlalchemy as sa
from alembic import op

revision = "7c1a4b9e2d05"
down_revision = "59285cbffe1c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("state", sa.String(length=100), nullable=True))
    op.add_column("properties", sa.Column("postcode", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("properties", "postcode")
    op.drop_column("properties", "state")
