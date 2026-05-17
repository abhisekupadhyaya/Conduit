# conduit/supervisor/schemas/decisions.py
"""Supervisor decision-queue surface schemas (Spec §8 "Supervisor
decisions" / §7.4). ``extra="forbid"`` everywhere — ONLY the curated
decision-facing fields are serialized (no raw FK ids beyond the stable
references the supervisor needs to act). The queue card carries the AI
recommendation + its per-action detail + the supervisor-SLA countdown
DEADLINE (ISO) + ``cycle_count``; a duty-manager hard-escalation is flagged
``non_time_boxed`` (D21 — the backstop is NOT time-boxed)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class RecommendationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str                       # ck_rec_action vocabulary
    rationale_text: str
    # Per-action detail (the thin ``rec_*`` row), curated by action. Only
    # the keys relevant to ``action`` are present.
    detail: dict


class DecisionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    escalation_id: str
    child_id: str
    trigger: str                      # triage_flag | stall | servicer_raised
    state: str
    cycle_count: int
    # The supervisor-SLA countdown deadline (the pending ``supervisor_sla``
    # Timer's ``fire_at``); None when there is no live timer (e.g. a
    # hard-escalated, non-time-boxed item).
    supervisor_sla_deadline: dt.datetime | None = None
    # D21: a duty-manager hard-escalation is NOT time-boxed.
    non_time_boxed: bool
    recommendation: RecommendationOut | None = None


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # approve → execute the STORED recommendation verbatim (silence ≡
    # approve is structural). edit/override → execute the supervisor-
    # supplied action + payload instead.
    action: str                       # approve | edit | override
    payload: dict | None = None


class ResolveOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    escalation_id: str
    state: str
    resolved_by_account_id: str | None = None
