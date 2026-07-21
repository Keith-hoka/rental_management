"""add user phone and lease tenant roster

Revision ID: b5d49658f834
Revises: e3cae689b06e
Create Date: 2026-07-21 13:39:18.768342

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b5d49658f834"
down_revision: Union[str, Sequence[str], None] = "e3cae689b06e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("leases", sa.Column("tenant_phone", sa.String(length=50), nullable=True))
    # co_tenants is NOT NULL; backfill existing rows via a temporary server
    # default, then drop it to match the model (which has no server_default).
    op.add_column(
        "leases",
        sa.Column("co_tenants", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("leases", "co_tenants", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("leases", "co_tenants")
    op.drop_column("leases", "tenant_phone")
    op.drop_column("users", "phone")
