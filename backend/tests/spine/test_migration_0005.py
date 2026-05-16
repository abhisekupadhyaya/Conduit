import pytest
from sqlalchemy import inspect
from conduit.shared.models import SLAPreset, EscalationLadder


def test_sla_preset_columns():
    cols = {c.name for c in inspect(SLAPreset).columns}
    assert cols == {"id", "property_id", "tier", "accept_window_seconds",
                    "fulfilment_sla_seconds", "supervisor_sla_seconds",
                    "status", "created_at", "updated_at"}


def test_escalation_ladder_columns():
    cols = {c.name for c in inspect(EscalationLadder).columns}
    assert cols == {"id", "property_id", "duty_manager_account_id",
                    "n_cycle_bound", "status", "created_at", "updated_at"}
