import pytest
from sqlalchemy import inspect
from conduit.shared.models import SLAPreset, EscalationLadder
from conduit.shared.models import WorkOrder, Timer, Escalation
from conduit.shared.models import (Recommendation, RecReassign, RecRelocate,
    RecExtendSla, RecApprove, RecDeny, RecBroadcast)
from conduit.shared.models import Glitch, CrossDeptNotification
from conduit.shared.models import ChildSubRequest, IssueCode


def test_sla_preset_columns():
    cols = {c.name for c in inspect(SLAPreset).columns}
    assert cols == {"id", "property_id", "tier", "accept_window_seconds",
                    "fulfilment_sla_seconds", "supervisor_sla_seconds",
                    "status", "created_at", "updated_at"}


def test_escalation_ladder_columns():
    cols = {c.name for c in inspect(EscalationLadder).columns}
    assert cols == {"id", "property_id", "duty_manager_account_id",
                    "n_cycle_bound", "status", "created_at", "updated_at"}


def test_work_order_columns():
    cols = {c.name for c in inspect(WorkOrder).columns}
    assert cols == {"id", "child_id", "kind", "routing_model",
                    "assigned_servicer_id", "accountable_owner_id",
                    "section_id", "priority_tier", "queue_position", "state",
                    "completion_notes", "created_at", "updated_at"}


def test_timer_columns():
    cols = {c.name for c in inspect(Timer).columns}
    assert cols == {"id", "type", "child_id", "work_order_id", "escalation_id",
                    "fire_at", "state", "cycle", "created_at"}


def test_escalation_columns():
    cols = {c.name for c in inspect(Escalation).columns}
    assert cols == {"id", "child_id", "trigger", "state", "cycle_count",
                    "raised_by_account_id", "resolved_by_account_id",
                    "created_at", "resolved_at"}


def test_recommendation_family():
    base = {c.name for c in inspect(Recommendation).columns}
    assert base == {"escalation_id","action","rationale_text","created_at"}
    assert {c.name for c in inspect(RecReassign).columns} == {"recommendation_escalation_id","target_account_id"}
    assert {c.name for c in inspect(RecRelocate).columns} == {"recommendation_escalation_id","target_room_id"}
    assert {c.name for c in inspect(RecExtendSla).columns} == {"recommendation_escalation_id","extend_seconds"}
    for m in (RecApprove, RecDeny, RecBroadcast):
        assert {c.name for c in inspect(m).columns} == {"recommendation_escalation_id"}


def test_glitch_columns():
    assert {c.name for c in inspect(Glitch).columns} == {"id","child_id","state",
        "opened_from","recovery_owed","recovery_cost","created_at","closed_at"}


def test_cross_dept_columns():
    assert {c.name for c in inspect(CrossDeptNotification).columns} == {"id",
        "source_work_order_id","target_department","child_id","reason","state","created_at"}


def test_child_additive_columns():
    cols = {c.name for c in inspect(ChildSubRequest).columns}
    assert {"priority_tier","closure","revised_eta","predecessor_child_id"} <= cols


def test_child_state_check_widened():
    ck = next(c for c in ChildSubRequest.__table__.constraints
              if getattr(c, "name", "") == "ck_child_state")
    txt = str(ck.sqltext)
    for s in ("routing","pushed","broadcast","accepted","in_progress",
              "done_pending_confirm","cancelled"):
        assert s in txt


def test_issue_code_sla_fk():
    assert "sla_preset_id" in {c.name for c in inspect(IssueCode).columns}


from conduit.shared.models import Event

def test_event_type_extended():
    ck = next(c for c in Event.__table__.constraints
              if getattr(c, "name", "") == "ck_event_type")
    txt = str(ck.sqltext)
    for t in ("work_order_created","work_order_completed","child_routed",
              "child_closed_confirmed","escalation_opened","escalation_resolved",
              "recommendation_created","glitch_opened","glitch_closed",
              "cross_dept_notified","timer_fired","sla_preset_created",
              "escalation_ladder_created"):
        assert t in txt
