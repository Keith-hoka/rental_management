"""add lease renewed_from

Revision ID: 0e4536ea7e9a
Revises: b83f5c0a1e47
Create Date: 2026-07-23 00:37:22.248459

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0e4536ea7e9a"
down_revision: Union[str, Sequence[str], None] = "b83f5c0a1e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("leases", sa.Column("renewed_from_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_leases_renewed_from_id_leases", "leases", "leases", ["renewed_from_id"], ["id"]
    )
    op.create_index("ix_leases_renewed_from_id", "leases", ["renewed_from_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_leases_renewed_from_id", table_name="leases")
    op.drop_constraint("fk_leases_renewed_from_id_leases", "leases", type_="foreignkey")
    op.drop_column("leases", "renewed_from_id")
