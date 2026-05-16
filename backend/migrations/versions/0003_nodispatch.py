"""nodispatch

Revision ID: 0003_nodispatch
Revises: 0002
Create Date: 2026-05-16
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_nodispatch"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_EVENT_TYPES = "type in ('stay_created','stay_ended','guest_relocated')"
_NEW_EVENT_TYPES = (
    "type in ('stay_created','stay_ended','guest_relocated',"
    "'request_created','child_triaged','child_answered',"
    "'child_deferred','child_parked','child_closed','child_reopened')"
)


def upgrade() -> None:
    op.create_table(
        "issue_code",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("department", sa.String(), nullable=False),
        sa.Column("fulfilment_mode", sa.String(), nullable=False),
        sa.Column("routing_model", sa.String(), nullable=False),
        sa.Column("intent_kind", sa.String(), server_default="service",
                  nullable=False),
        sa.Column("is_reservation_mutation", sa.Boolean(),
                  server_default="false", nullable=False),
        sa.Column("status", sa.String(), server_default="active",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("fulfilment_mode in ('dispatch','no_dispatch')",
                           name="ck_issue_code_mode"),
        sa.CheckConstraint("intent_kind in ('service','problem_report')",
                           name="ck_issue_code_intent"),
        sa.CheckConstraint(
            "routing_model in ('section_pooled','skill_matched','none')",
            name="ck_issue_code_routing"),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_issue_code_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_issue_code_lower_code", "issue_code",
                    [sa.text("lower(code)")], unique=True)
    op.create_table(
        "kb_entry",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="active",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_kb_entry_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "request",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("guest_account_id", sa.UUID(), nullable=False),
        sa.Column("stay_id", sa.UUID(), nullable=False),
        sa.Column("raw_text", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), server_default="text",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("channel in ('text')", name="ck_request_channel"),
        sa.ForeignKeyConstraint(["guest_account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["stay_id"], ["stay.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "child_sub_request",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("issue_code_id", sa.UUID(), nullable=True),
        sa.Column("uncategorized", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("fulfilment_mode", sa.String(), nullable=True),
        sa.Column("is_problem_report", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.Column("state", sa.String(), server_default="intake",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "fulfilment_mode is null or "
            "fulfilment_mode in ('dispatch','no_dispatch')",
            name="ck_child_mode"),
        sa.CheckConstraint("outcome in ('auto','clarify','flag','no_dispatch')",
                           name="ck_child_outcome"),
        sa.CheckConstraint(
            "state in ('intake','triaged','answered','concierge_queue',"
            "'closed','reopened')", name="ck_child_state"),
        sa.ForeignKeyConstraint(["issue_code_id"], ["issue_code.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["request.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "event_request_created",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["request.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    for t in ("event_child_triaged", "event_child_deferred",
              "event_child_parked", "event_child_closed",
              "event_child_reopened"):
        op.create_table(
            t,
            sa.Column("event_id", sa.UUID(), nullable=False),
            sa.Column("child_id", sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
            sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
            sa.PrimaryKeyConstraint("event_id"),
        )
    op.create_table(
        "no_dispatch_resolution",
        sa.Column("child_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("answer_text", sa.String(), nullable=True),
        sa.Column("helpful", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("helpful is null or helpful in ('yes','no')",
                           name="ck_ndr_helpful"),
        sa.CheckConstraint("mode in ('grounded_answer','human_deferral')",
                           name="ck_ndr_mode"),
        sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
        sa.PrimaryKeyConstraint("child_id"),
    )
    op.create_table(
        "event_child_answered",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("child_id", sa.UUID(), nullable=False),
        sa.Column("resolution_child_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.ForeignKeyConstraint(["resolution_child_id"],
                                ["no_dispatch_resolution.child_id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "nd_provenance_field",
        sa.Column("resolution_child_id", sa.UUID(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("claimed_used", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.CheckConstraint(
            "field_name in ('room_label','section_label','check_in',"
            "'check_out','stay_status')", name="ck_ndpf_field"),
        sa.ForeignKeyConstraint(["resolution_child_id"],
                                ["no_dispatch_resolution.child_id"]),
        sa.PrimaryKeyConstraint("resolution_child_id", "field_name"),
    )
    op.create_table(
        "nd_provenance_kb",
        sa.Column("resolution_child_id", sa.UUID(), nullable=False),
        sa.Column("kb_entry_id", sa.UUID(), nullable=False),
        sa.Column("claimed_used", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.ForeignKeyConstraint(["kb_entry_id"], ["kb_entry.id"]),
        sa.ForeignKeyConstraint(["resolution_child_id"],
                                ["no_dispatch_resolution.child_id"]),
        sa.PrimaryKeyConstraint("resolution_child_id", "kb_entry_id"),
    )
    # Extend the event.type CHECK additively (autogenerate cannot detect a
    # CHECK-text change — hand-written drop + recreate of the merged
    # constraint name ck_event_type).
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint("ck_event_type", "event", _NEW_EVENT_TYPES)


def downgrade() -> None:
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint("ck_event_type", "event", _OLD_EVENT_TYPES)
    op.drop_table("nd_provenance_kb")
    op.drop_table("nd_provenance_field")
    op.drop_table("event_child_answered")
    op.drop_table("no_dispatch_resolution")
    for t in ("event_child_reopened", "event_child_closed",
              "event_child_parked", "event_child_deferred",
              "event_child_triaged"):
        op.drop_table(t)
    op.drop_table("event_request_created")
    op.drop_table("child_sub_request")
    op.drop_table("request")
    op.drop_table("kb_entry")
    op.drop_index("uq_issue_code_lower_code", table_name="issue_code")
    op.drop_table("issue_code")
