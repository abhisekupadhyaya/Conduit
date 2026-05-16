"""staffing

Revision ID: 0004_staffing
Revises: 0003_nodispatch
Create Date: 2026-05-16
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_staffing"
down_revision: str | None = "0003_nodispatch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_EVENT_TYPES = (
    "type in ('stay_created','stay_ended','guest_relocated',"
    "'request_created','child_triaged','child_answered',"
    "'child_deferred','child_parked','child_closed','child_reopened')"
)
_NEW_EVENT_TYPES = (
    "type in ('stay_created','stay_ended','guest_relocated',"
    "'request_created','child_triaged','child_answered',"
    "'child_deferred','child_parked','child_closed','child_reopened',"
    "'staff_profile_created','staff_profile_updated',"
    "'staff_skills_set','roster_created','roster_updated',"
    "'assignment_created','assignment_updated','presence_changed')"
)


def upgrade() -> None:
    op.create_table(
        "staff_profile",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("staff_class", sa.String(), nullable=False),
        sa.Column("presence", sa.String(), server_default="working",
                  nullable=False),
        sa.Column("presence_set_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("status", sa.String(), server_default="active",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "staff_class in ('housekeeping','engineering','room_service',"
            "'concierge','runner')", name="ck_staff_profile_class"),
        sa.CheckConstraint("presence in ('working','on_break','off')",
                           name="ck_staff_profile_presence"),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_staff_profile_status"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.create_table(
        "staff_skill",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("skill", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("account_id", "skill"),
    )
    op.create_table(
        "roster",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("shift_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shift_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), server_default="active",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("shift_end > shift_start",
                           name="ck_roster_window"),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_roster_status"),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "roster_assignment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("roster_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("section_id", sa.UUID(), nullable=True),
        sa.Column("assignment", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="active",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("assignment in ('owner','backup','member')",
                           name="ck_assignment_role"),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_assignment_status"),
        sa.CheckConstraint(
            "assignment not in ('owner','backup') OR section_id IS NOT NULL",
            name="ck_assignment_owner_needs_section"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["roster_id"], ["roster.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["section.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_active_owner_per_section", "roster_assignment",
        ["roster_id", "section_id"], unique=True,
        postgresql_where=sa.text("assignment = 'owner' AND status = 'active'"),
    )
    op.create_table(
        "event_staff_profile_created",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "event_staff_profile_updated",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "event_staff_skills_set",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "event_roster_created",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("roster_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.ForeignKeyConstraint(["roster_id"], ["roster.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "event_roster_updated",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("roster_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.ForeignKeyConstraint(["roster_id"], ["roster.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "event_assignment_created",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"],
                                ["roster_assignment.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "event_assignment_updated",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"],
                                ["roster_assignment.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "event_presence_changed",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    # Extend the event.type CHECK additively (autogenerate cannot detect a
    # CHECK-text change — hand-written drop + recreate of the merged
    # constraint name ck_event_type, mirroring 0003_nodispatch).
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint("ck_event_type", "event", _NEW_EVENT_TYPES)


def downgrade() -> None:
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint("ck_event_type", "event", _OLD_EVENT_TYPES)
    op.drop_table("event_presence_changed")
    op.drop_table("event_assignment_updated")
    op.drop_table("event_assignment_created")
    op.drop_table("event_roster_updated")
    op.drop_table("event_roster_created")
    op.drop_table("event_staff_skills_set")
    op.drop_table("event_staff_profile_updated")
    op.drop_table("event_staff_profile_created")
    op.drop_index(
        "uq_active_owner_per_section", table_name="roster_assignment",
        postgresql_where=sa.text("assignment = 'owner' AND status = 'active'"),
    )
    op.drop_table("roster_assignment")
    op.drop_table("roster")
    op.drop_table("staff_skill")
    op.drop_table("staff_profile")
