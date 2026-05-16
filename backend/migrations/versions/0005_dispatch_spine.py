"""0005 dispatch spine

Revision ID: 0005_dispatch
Revises: 0004_staffing
Create Date: 2026-05-16

Dispatch & Escalation Spine physical schema (D14/D15/D19/D21/D43/D44 and the
AD-series dispatch ADRs). Hand-audited from autogenerate:

  * 8 new core tables (sla_preset, escalation_ladder, work_order, timer,
    escalation, recommendation, glitch, cross_dept_notification) + 6
    recommendation detail tables + 23 new event detail tables.
  * Two partial-unique indexes (uq_sla_active_tier,
    uq_ladder_active_property) + ix_timer_state_fire_at.
  * 4 additive child_sub_request columns + issue_code.sla_preset_id, with
    their named FKs.
  * Drop + recreate of the ck_child_state and ck_event_type CHECKs with the
    widened/extended strings (autogenerate cannot detect a CHECK-text change
    — mirrors the 0003/0004 hand-written idiom), and the two new
    ck_child_closure / ck_child_tier CHECKs.

Removed autogenerate noise UNRELATED to A1-A6: autogenerate proposed dropping
``uq_issue_code_lower_code`` (a 0003 lower(code) expression index) and
``uq_stay_one_active_per_guest`` (a 0002 partial-unique index). Neither is
declared in ORM metadata, so autogenerate proposes the drop on EVERY run; both
predate this slice and are intentionally left untouched here.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_dispatch"
down_revision: str | None = "0004_staffing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- CHECK-text deltas (autogenerate cannot diff CHECK bodies) -------------
# ck_child_state: prior (0004 / pre-A5) value, restored verbatim on downgrade.
_OLD_CHILD_STATE = (
    "state in ('intake','triaged','answered','concierge_queue',"
    "'closed','reopened')"
)
# ck_child_state: widened value (A5 — dispatch lifecycle states).
_NEW_CHILD_STATE = (
    "state in ('intake','triaged','clarifying','routing','pushed',"
    "'broadcast','accepted','in_progress','done_pending_confirm','answered',"
    "'concierge_queue','closed','reopened','cancelled')"
)
_CK_CHILD_CLOSURE = (
    "closure is null or closure in ('pending','confirmed','reopened','aging')"
)
_CK_CHILD_TIER = (
    "priority_tier is null or priority_tier in ('P1','P2','P3','P4')"
)
# ck_event_type: prior (0004 staffing-extended) value — restored verbatim on
# downgrade — and the A6 dispatch-extended value.
_OLD_EVENT_TYPES = (
    "type in ('stay_created','stay_ended','guest_relocated',"
    "'request_created','child_triaged','child_answered',"
    "'child_deferred','child_parked','child_closed','child_reopened',"
    "'staff_profile_created','staff_profile_updated',"
    "'staff_skills_set','roster_created','roster_updated',"
    "'assignment_created','assignment_updated','presence_changed')"
)
_NEW_EVENT_TYPES = (
    "type in ('stay_created','stay_ended','guest_relocated',"
    "'request_created','child_triaged','child_answered',"
    "'child_deferred','child_parked','child_closed','child_reopened',"
    "'staff_profile_created','staff_profile_updated',"
    "'staff_skills_set','roster_created','roster_updated',"
    "'assignment_created','assignment_updated','presence_changed',"
    "'work_order_created','work_order_pushed','work_order_broadcast',"
    "'work_order_accepted','work_order_in_progress',"
    "'work_order_completed','work_order_cancelled','child_routed',"
    "'child_done_pending_confirm','child_closed_confirmed',"
    "'child_reopened_by_guest','child_cancelled','escalation_opened',"
    "'escalation_resolved','recommendation_created','glitch_opened',"
    "'glitch_closed','cross_dept_notified','timer_fired',"
    "'sla_preset_created','sla_preset_updated',"
    "'escalation_ladder_created','escalation_ladder_updated')"
)


def upgrade() -> None:
    # --- CONFIG tables (D15/D21) -----------------------------------------
    op.create_table(
        "escalation_ladder",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("duty_manager_account_id", sa.UUID(), nullable=False),
        sa.Column("n_cycle_bound", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), server_default="active",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_ladder_status"),
        sa.CheckConstraint("n_cycle_bound > 0", name="ck_ladder_nbound"),
        sa.ForeignKeyConstraint(["duty_manager_account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ladder_active_property", "escalation_ladder", ["property_id"],
        unique=True, postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "sla_preset",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("accept_window_seconds", sa.Integer(), nullable=False),
        sa.Column("fulfilment_sla_seconds", sa.Integer(), nullable=False),
        sa.Column("supervisor_sla_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), server_default="active",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_sla_status"),
        sa.CheckConstraint("tier in ('P1','P2','P3','P4')",
                           name="ck_sla_tier"),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_sla_active_tier", "sla_preset", ["property_id", "tier"],
        unique=True, postgresql_where=sa.text("status = 'active'"),
    )

    # --- core dispatch/escalation tables ---------------------------------
    op.create_table(
        "escalation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("child_id", sa.UUID(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("state", sa.String(), server_default="open",
                  nullable=False),
        sa.Column("cycle_count", sa.Integer(), server_default="0",
                  nullable=False),
        sa.Column("raised_by_account_id", sa.UUID(), nullable=True),
        sa.Column("resolved_by_account_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state in ('open','approved','edited','overridden',"
            "'auto_proceeded','hard_escalated')", name="ck_esc_state"),
        sa.CheckConstraint(
            "trigger in ('triage_flag','stall','servicer_raised')",
            name="ck_esc_trigger"),
        sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
        sa.ForeignKeyConstraint(["raised_by_account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["resolved_by_account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "glitch",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("child_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(), server_default="open",
                  nullable=False),
        sa.Column("opened_from", sa.String(), nullable=False),
        sa.Column("recovery_owed", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.Column("recovery_cost", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("opened_from in ('problem_report','dispute')",
                           name="ck_glitch_origin"),
        sa.CheckConstraint(
            "state in ('open','held_open','auto_closed','closed')",
            name="ck_glitch_state"),
        sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("child_id"),
    )
    op.create_table(
        "work_order",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("child_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("routing_model", sa.String(), nullable=False),
        sa.Column("assigned_servicer_id", sa.UUID(), nullable=True),
        sa.Column("accountable_owner_id", sa.UUID(), nullable=True),
        sa.Column("section_id", sa.UUID(), nullable=True),
        sa.Column("priority_tier", sa.String(), nullable=False),
        sa.Column("queue_position", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(), server_default="created",
                  nullable=False),
        sa.Column("completion_notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind in ('dispatch','human_concierge_answer')",
                           name="ck_wo_kind"),
        sa.CheckConstraint("priority_tier in ('P1','P2','P3','P4')",
                           name="ck_wo_tier"),
        sa.CheckConstraint(
            "routing_model in ('section_pooled','skill_matched')",
            name="ck_wo_model"),
        sa.CheckConstraint(
            "state in ('created','pushed','broadcast','accepted',"
            "'in_progress','completed','cancelled')", name="ck_wo_state"),
        sa.ForeignKeyConstraint(["accountable_owner_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["assigned_servicer_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["section.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("child_id"),
    )
    op.create_table(
        "cross_dept_notification",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_work_order_id", sa.UUID(), nullable=False),
        sa.Column("target_department", sa.String(), nullable=False),
        sa.Column("child_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("state", sa.String(), server_default="open",
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("state in ('open','acknowledged')",
                           name="ck_xdn_state"),
        sa.CheckConstraint(
            "target_department in ('housekeeping','engineering',"
            "'room_service','concierge','front_desk','runner')",
            name="ck_xdn_dept"),
        sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
        sa.ForeignKeyConstraint(["source_work_order_id"], ["work_order.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "recommendation",
        sa.Column("escalation_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("rationale_text", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "action in ('reassign','broadcast','relocate',"
            "'extend_sla','approve','deny')", name="ck_rec_action"),
        sa.ForeignKeyConstraint(["escalation_id"], ["escalation.id"]),
        sa.PrimaryKeyConstraint("escalation_id"),
    )
    op.create_table(
        "timer",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("child_id", sa.UUID(), nullable=True),
        sa.Column("work_order_id", sa.UUID(), nullable=True),
        sa.Column("escalation_id", sa.UUID(), nullable=True),
        sa.Column("fire_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(), server_default="pending",
                  nullable=False),
        sa.Column("cycle", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("state in ('pending','fired','cancelled')",
                           name="ck_timer_state"),
        sa.CheckConstraint(
            "type in ('accept_window','fulfilment_sla',"
            "'supervisor_sla','backstop_cycle')", name="ck_timer_type"),
        sa.CheckConstraint(
            "(child_id is not null)::int + (work_order_id is not null)::int "
            "+ (escalation_id is not null)::int = 1",
            name="ck_timer_one_subject"),
        sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
        sa.ForeignKeyConstraint(["escalation_id"], ["escalation.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_order.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_timer_state_fire_at", "timer", ["state", "fire_at"],
        unique=False,
    )

    # --- recommendation detail tables (6) --------------------------------
    op.create_table(
        "rec_approve",
        sa.Column("recommendation_escalation_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_escalation_id"],
                                ["recommendation.escalation_id"]),
        sa.PrimaryKeyConstraint("recommendation_escalation_id"),
    )
    op.create_table(
        "rec_broadcast",
        sa.Column("recommendation_escalation_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_escalation_id"],
                                ["recommendation.escalation_id"]),
        sa.PrimaryKeyConstraint("recommendation_escalation_id"),
    )
    op.create_table(
        "rec_deny",
        sa.Column("recommendation_escalation_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_escalation_id"],
                                ["recommendation.escalation_id"]),
        sa.PrimaryKeyConstraint("recommendation_escalation_id"),
    )
    op.create_table(
        "rec_extend_sla",
        sa.Column("extend_seconds", sa.Integer(), nullable=False),
        sa.Column("recommendation_escalation_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_escalation_id"],
                                ["recommendation.escalation_id"]),
        sa.PrimaryKeyConstraint("recommendation_escalation_id"),
    )
    op.create_table(
        "rec_reassign",
        sa.Column("target_account_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_escalation_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_escalation_id"],
                                ["recommendation.escalation_id"]),
        sa.ForeignKeyConstraint(["target_account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("recommendation_escalation_id"),
    )
    op.create_table(
        "rec_relocate",
        sa.Column("target_room_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_escalation_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_escalation_id"],
                                ["recommendation.escalation_id"]),
        sa.ForeignKeyConstraint(["target_room_id"], ["room.id"]),
        sa.PrimaryKeyConstraint("recommendation_escalation_id"),
    )

    # --- new event detail tables (23) ------------------------------------
    # 18 with a single typed subject FK ...
    for _t, _fk_col, _fk_ref in (
        ("event_work_order_created", "work_order_id", "work_order.id"),
        ("event_work_order_pushed", "work_order_id", "work_order.id"),
        ("event_work_order_broadcast", "work_order_id", "work_order.id"),
        ("event_work_order_accepted", "work_order_id", "work_order.id"),
        ("event_work_order_in_progress", "work_order_id", "work_order.id"),
        ("event_work_order_completed", "work_order_id", "work_order.id"),
        ("event_work_order_cancelled", "work_order_id", "work_order.id"),
        ("event_escalation_opened", "escalation_id", "escalation.id"),
        ("event_escalation_resolved", "escalation_id", "escalation.id"),
        ("event_glitch_opened", "glitch_id", "glitch.id"),
        ("event_glitch_closed", "glitch_id", "glitch.id"),
        ("event_timer_fired", "timer_id", "timer.id"),
        ("event_sla_preset_created", "sla_preset_id", "sla_preset.id"),
        ("event_sla_preset_updated", "sla_preset_id", "sla_preset.id"),
        ("event_escalation_ladder_created", "escalation_ladder_id",
         "escalation_ladder.id"),
        ("event_escalation_ladder_updated", "escalation_ladder_id",
         "escalation_ladder.id"),
        ("event_cross_dept_notified", "cross_dept_notification_id",
         "cross_dept_notification.id"),
        ("event_recommendation_created", "recommendation_escalation_id",
         "recommendation.escalation_id"),
    ):
        op.create_table(
            _t,
            sa.Column("event_id", sa.UUID(), nullable=False),
            sa.Column(_fk_col, sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint([_fk_col], [_fk_ref]),
            sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
            sa.PrimaryKeyConstraint("event_id"),
        )
    # ... and 5 child-subject events (_ChildEvent shape).
    for _t in (
        "event_child_routed",
        "event_child_done_pending_confirm",
        "event_child_closed_confirmed",
        "event_child_reopened_by_guest",
        "event_child_cancelled",
    ):
        op.create_table(
            _t,
            sa.Column("event_id", sa.UUID(), nullable=False),
            sa.Column("child_id", sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(["child_id"], ["child_sub_request.id"]),
            sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
            sa.PrimaryKeyConstraint("event_id"),
        )

    # --- additive child_sub_request columns (A5) -------------------------
    op.add_column("child_sub_request",
                  sa.Column("priority_tier", sa.String(), nullable=True))
    op.add_column("child_sub_request",
                  sa.Column("closure", sa.String(), nullable=True))
    op.add_column("child_sub_request",
                  sa.Column("revised_eta", sa.DateTime(timezone=True),
                            nullable=True))
    op.add_column("child_sub_request",
                  sa.Column("predecessor_child_id", sa.UUID(),
                            nullable=True))
    op.create_foreign_key(
        "fk_child_predecessor", "child_sub_request", "child_sub_request",
        ["predecessor_child_id"], ["id"],
    )
    op.add_column("issue_code",
                  sa.Column("sla_preset_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_issue_code_sla_preset", "issue_code", "sla_preset",
        ["sla_preset_id"], ["id"],
    )

    # --- CHECK-text widening (A5/A6) — autogenerate cannot diff CHECK
    # bodies; hand-written drop + recreate mirroring 0003/0004. ------------
    op.drop_constraint("ck_child_state", "child_sub_request", type_="check")
    op.create_check_constraint(
        "ck_child_state", "child_sub_request", _NEW_CHILD_STATE)
    op.create_check_constraint(
        "ck_child_closure", "child_sub_request", _CK_CHILD_CLOSURE)
    op.create_check_constraint(
        "ck_child_tier", "child_sub_request", _CK_CHILD_TIER)
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint("ck_event_type", "event", _NEW_EVENT_TYPES)


def downgrade() -> None:
    # Restore the PRIOR (0004-state) CHECK strings VERBATIM and drop the
    # A5-introduced ck_child_closure / ck_child_tier constraints.
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint("ck_event_type", "event", _OLD_EVENT_TYPES)
    op.drop_constraint("ck_child_tier", "child_sub_request", type_="check")
    op.drop_constraint("ck_child_closure", "child_sub_request", type_="check")
    op.drop_constraint("ck_child_state", "child_sub_request", type_="check")
    op.create_check_constraint(
        "ck_child_state", "child_sub_request", _OLD_CHILD_STATE)

    op.drop_constraint("fk_issue_code_sla_preset", "issue_code",
                       type_="foreignkey")
    op.drop_column("issue_code", "sla_preset_id")
    op.drop_constraint("fk_child_predecessor", "child_sub_request",
                       type_="foreignkey")
    op.drop_column("child_sub_request", "predecessor_child_id")
    op.drop_column("child_sub_request", "revised_eta")
    op.drop_column("child_sub_request", "closure")
    op.drop_column("child_sub_request", "priority_tier")

    # New event detail tables (no inter-FKs among them — order free).
    for _t in (
        "event_child_cancelled",
        "event_child_reopened_by_guest",
        "event_child_closed_confirmed",
        "event_child_done_pending_confirm",
        "event_child_routed",
        "event_recommendation_created",
        "event_cross_dept_notified",
        "event_escalation_ladder_updated",
        "event_escalation_ladder_created",
        "event_sla_preset_updated",
        "event_sla_preset_created",
        "event_timer_fired",
        "event_glitch_closed",
        "event_glitch_opened",
        "event_escalation_resolved",
        "event_escalation_opened",
        "event_work_order_cancelled",
        "event_work_order_completed",
        "event_work_order_in_progress",
        "event_work_order_accepted",
        "event_work_order_broadcast",
        "event_work_order_pushed",
        "event_work_order_created",
    ):
        op.drop_table(_t)

    # Recommendation detail tables (FK -> recommendation).
    op.drop_table("rec_relocate")
    op.drop_table("rec_reassign")
    op.drop_table("rec_extend_sla")
    op.drop_table("rec_deny")
    op.drop_table("rec_broadcast")
    op.drop_table("rec_approve")

    # Core tables — FK-safe order: timer -> {work_order, escalation};
    # cross_dept_notification -> work_order; recommendation -> escalation;
    # glitch/work_order/escalation -> child_sub_request.
    op.drop_index("ix_timer_state_fire_at", table_name="timer")
    op.drop_table("timer")
    op.drop_table("recommendation")
    op.drop_table("cross_dept_notification")
    op.drop_table("work_order")
    op.drop_table("glitch")
    op.drop_table("escalation")

    op.drop_index(
        "uq_sla_active_tier", table_name="sla_preset",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_table("sla_preset")
    op.drop_index(
        "uq_ladder_active_property", table_name="escalation_ladder",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_table("escalation_ladder")
