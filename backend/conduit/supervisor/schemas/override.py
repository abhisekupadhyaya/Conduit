# conduit/supervisor/schemas/override.py
"""Supervisor task-explorer + override surface schemas (Spec §8 "Supervisor
children/override" — D6 god-mode). ``extra="forbid"`` everywhere — a
malformed body is a clean 422; ONLY the curated decision-facing fields are
serialized (no raw internal columns beyond the stable references the
supervisor needs to act).

This is a NEW file: ``schemas/decisions.py`` is E3's and is left untouched
(Resolution E / clean separation)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WorkOrderRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_servicer_id: str | None = None
    # Servicer display name (the UI renders this, not the raw id).
    servicer_name: str | None = None
    accountable_owner_id: str | None = None
    state: str


class EscalationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    escalation_id: str
    trigger: str
    state: str


class GlitchRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    glitch_id: str
    state: str


class ChildExplorerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child_id: str
    # The child's issue-code label (None = uncategorized); the UI renders
    # this, never the raw child_id.
    issue_label: str | None = None
    state: str
    work_order: WorkOrderRef | None = None
    escalation: EscalationRef | None = None
    glitch: GlitchRef | None = None


class TakeoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Optional: absent → the acting supervisor becomes the assignee;
    # present → hand the work to this named servicer.
    target_servicer_id: str | None = None


class ReassignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Required: reassign is an explicit hand-to-target.
    target_servicer_id: str


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Cancel carries no params — the body is an empty (extra="forbid")
    # object so a stray key is still a clean 422.


class OverrideOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child_id: str
    # The post-action child state (set for ``cancel``; ``None`` for the
    # assignee-swap actions, which are not a child state change).
    child_state: str | None = None
    assigned_servicer_id: str | None = None
    accountable_owner_id: str | None = None
