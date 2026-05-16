"""stay binding

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def _ts(col):
    return sa.Column(col, sa.DateTime(timezone=True),
                     server_default=sa.text("now()"), nullable=False)


def _pk():
    return sa.Column("id", _UUID, primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def upgrade() -> None:
    op.create_table(
        "property", _pk(),
        sa.Column("name", sa.String(), nullable=False),
        _ts("created_at"), _ts("updated_at"))
    op.create_table(
        "section", _pk(),
        sa.Column("property_id", _UUID,
                  sa.ForeignKey("property.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        _ts("created_at"), _ts("updated_at"))
    op.create_table(
        "room", _pk(),
        sa.Column("section_id", _UUID,
                  sa.ForeignKey("section.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        _ts("created_at"), _ts("updated_at"))
    op.create_table(
        "stay", _pk(),
        sa.Column("guest_account_id", _UUID,
                  sa.ForeignKey("account.id"), nullable=False),
        sa.Column("room_id", _UUID, sa.ForeignKey("room.id"),
                  nullable=False),
        sa.Column("check_in", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_out", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False,
                  server_default="active"),
        _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("status in ('active','ended')",
                           name="ck_stay_status"))
    op.create_index(
        "uq_stay_one_active_per_guest", "stay", ["guest_account_id"],
        unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_table(
        "event", _pk(),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("actor_account_id", _UUID,
                  sa.ForeignKey("account.id"), nullable=True),
        _ts("at"),
        sa.CheckConstraint(
            "type in ('stay_created','stay_ended','guest_relocated')",
            name="ck_event_type"))
    for t, extra in (
        ("event_stay_created", []),
        ("event_stay_ended", []),
        ("event_guest_relocated", [
            sa.Column("from_room_id", _UUID,
                      sa.ForeignKey("room.id"), nullable=False),
            sa.Column("to_room_id", _UUID,
                      sa.ForeignKey("room.id"), nullable=False)]),
    ):
        op.create_table(
            t,
            sa.Column("event_id", _UUID, sa.ForeignKey("event.id"),
                      primary_key=True),
            sa.Column("stay_id", _UUID, sa.ForeignKey("stay.id"),
                      nullable=False),
            *extra)


def downgrade() -> None:
    for t in ("event_guest_relocated", "event_stay_ended",
              "event_stay_created", "event"):
        op.drop_table(t)
    op.drop_index("uq_stay_one_active_per_guest", table_name="stay")
    for t in ("stay", "room", "section", "property"):
        op.drop_table(t)
