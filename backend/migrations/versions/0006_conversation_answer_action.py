"""0006 conversation context + answer<->action seam

Revision ID: 0006_conv_aa
Revises: 0005_dispatch
Create Date: 2026-05-16

Additive on the spine: 2 detail tables (rec_apply_reservation_mutation,
event_reservation_mutated), 1 nullable child column (requested_checkout),
and 3 drop+recreate CHECK widenings (ck_rec_action, ck_event_type,
ck_ndr_mode) — autogenerate cannot detect CHECK-text changes, mirroring the
0003/0004/0005 hand-written idiom. No data migration; existing rows survive.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_conv_aa"
down_revision: str | None = "0005_dispatch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "child_sub_request",
        sa.Column("requested_checkout", sa.DateTime(timezone=True),
                  nullable=True))

    op.create_table(
        "rec_apply_reservation_mutation",
        sa.Column("recommendation_escalation_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("requested_value", sa.DateTime(timezone=True),
                  nullable=False),
        sa.CheckConstraint("field = 'check_out'",
                           name="ck_rec_apply_mutation_field"),
        sa.ForeignKeyConstraint(["recommendation_escalation_id"],
                                ["recommendation.escalation_id"]),
        sa.PrimaryKeyConstraint("recommendation_escalation_id"))

    op.create_table(
        "event_reservation_mutated",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("stay_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("old_value", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_value", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("field = 'check_out'",
                           name="ck_event_resv_mut_field"),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"]),
        sa.ForeignKeyConstraint(["stay_id"], ["stay.id"]),
        sa.PrimaryKeyConstraint("event_id"))

    # --- drop + recreate the 3 widened CHECKs (text change undetectable) ---
    op.drop_constraint("ck_rec_action", "recommendation", type_="check")
    op.create_check_constraint(
        "ck_rec_action", "recommendation",
        "action in ('reassign','broadcast','relocate','extend_sla',"
        "'approve','deny','apply_reservation_mutation')")

    op.drop_constraint("ck_ndr_mode", "no_dispatch_resolution",
                       type_="check")
    op.create_check_constraint(
        "ck_ndr_mode", "no_dispatch_resolution",
        "mode in ('grounded_answer','human_deferral','reservation_mutation')")

    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint(
        "ck_event_type", "event",
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
        "'escalation_ladder_created','escalation_ladder_updated',"
        "'reservation_mutated')")


def downgrade() -> None:
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint(
        "ck_event_type", "event",
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
        "'escalation_ladder_created','escalation_ladder_updated')")

    op.drop_constraint("ck_ndr_mode", "no_dispatch_resolution",
                       type_="check")
    op.create_check_constraint(
        "ck_ndr_mode", "no_dispatch_resolution",
        "mode in ('grounded_answer','human_deferral')")

    op.drop_constraint("ck_rec_action", "recommendation", type_="check")
    op.create_check_constraint(
        "ck_rec_action", "recommendation",
        "action in ('reassign','broadcast','relocate','extend_sla',"
        "'approve','deny')")

    op.drop_table("event_reservation_mutated")
    op.drop_table("rec_apply_reservation_mutation")
    op.drop_column("child_sub_request", "requested_checkout")
