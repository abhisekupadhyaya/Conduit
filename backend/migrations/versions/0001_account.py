"""account

Revision ID: 0001
Revises:
Create Date: 2026-05-16 04:23:56.081144
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.create_table(
        "account",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "role in ('guest','servicer','supervisor','duty_manager')",
            name="ck_account_role"),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_account_status"),
    )
    op.create_index("uq_account_username_lower", "account",
                     [sa.text("lower(username)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_account_username_lower", table_name="account")
    op.drop_table("account")
