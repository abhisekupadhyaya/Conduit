"""Guest dispatch response schemas (Spec §8). ``extra="forbid"``; ONLY the
curated guest-facing fields are serialized — no internal columns (no ids of
the work order / servicer / section, no routing model, no priority tier)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class DispatchCardOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child_id: str
    state: str
    issue_label: str | None = None
    assigned_servicer_name: str | None = None   # D17 — NAME, never the id
    revised_eta: dt.datetime | None = None
    glitch: bool = False


class ChildStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child_id: str
    state: str
