"""add ai_feature_consents

Revision ID: fae81f3c358b
Revises: 00cbeeefeadc
Create Date: 2026-08-14 12:34:39.804879

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fae81f3c358b"
down_revision: str | Sequence[str] | None = "00cbeeefeadc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_feature_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "feature",
            sa.Enum("clause_audit", "rent_ai", name="aifeature"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("disclosure_version", sa.String(length=20), nullable=False),
        sa.Column("acted_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["acted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq"),
    )
    op.create_index(
        op.f("ix_ai_feature_consents_organization_id"),
        "ai_feature_consents",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ai_feature_consents_organization_id"),
        table_name="ai_feature_consents",
    )
    op.drop_table("ai_feature_consents")
    sa.Enum(name="aifeature").drop(op.get_bind(), checkfirst=True)
