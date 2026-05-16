import pytest
from sqlalchemy import inspect
from conduit.shared.models import SLAPreset, EscalationLadder
from conduit.shared.models import WorkOrder, Timer, Escalation


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
