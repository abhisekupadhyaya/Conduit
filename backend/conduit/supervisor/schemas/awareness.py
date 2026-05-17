# conduit/supervisor/schemas/awareness.py
"""Supervisor awareness-stream surface schema (Spec §8/§9 — the first
event read model, polled). ``extra="forbid"`` everywhere: ONLY the
curated watch-facing labels are serialized (the stable references the
supervisor needs to read the stream — no raw internal-id leak beyond
that). ONE composite response with the four nested section models
(incoming · task delegation · servicer recent work · open glitches);
every item is derived FROM the append-only ``event``+detail log."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class IncomingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    escalation_id: str
    child_id: str
    trigger: str                      # triage_flag | stall | servicer_raised
    at: dt.datetime                   # the escalation_opened event time


class DelegationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_order_id: str
    child_id: str
    servicer_id: str | None = None
    at: dt.datetime                   # the most-recent delegation event time


class RecentWorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_order_id: str
    child_id: str
    servicer_id: str | None = None
    at: dt.datetime                   # the most-recent activity event time


class OpenGlitchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    glitch_id: str
    child_id: str
    opened_from: str                  # problem_report | dispute
    at: dt.datetime                   # the glitch_opened event time


class AwarenessOut(BaseModel):
    """The ONE composite projection (Spec §8/§9). Each section's item set
    is driven by EMITTED EVENTS; ``open_glitches`` reflects glitch_opened
    MINUS glitch_closed (a glitch disappears once closed)."""
    model_config = ConfigDict(extra="forbid")
    incoming: list[IncomingItem]
    task_delegation: list[DelegationItem]
    servicer_recent_work: list[RecentWorkItem]
    open_glitches: list[OpenGlitchItem]
