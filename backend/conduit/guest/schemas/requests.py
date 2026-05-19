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
    # Spec §7.4 / §9.3 / D22 — a live sibling whose stay was re-bound is
    # proactively told: the guest's CURRENT room label once a relocation
    # occurred for this stay (a ``guest_relocated`` event exists), else
    # None. Additive output; default None keeps every existing card
    # construction valid + ``extra="forbid"`` intact.
    relocated_to: str | None = None


class ChildStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child_id: str
    state: str
