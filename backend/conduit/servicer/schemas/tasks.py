"""Servicer task surface schemas (Spec §8 "Servicer"). ``extra="forbid"``;
ONLY the curated servicer-facing fields are serialized — no routing model,
no assignee/owner ids, no section id (internal). The polled queue card
carries live SLA / accept-window deadlines (D23)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class TaskOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_order_id: str
    child_id: str
    kind: str                    # 'pushed' (owned) | 'claimable' (in-zone)
    state: str
    priority_tier: str
    issue_label: str | None = None
    accept_window_deadline: dt.datetime | None = None
    fulfilment_sla_deadline: dt.datetime | None = None


class CompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = None


class RaiseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str
