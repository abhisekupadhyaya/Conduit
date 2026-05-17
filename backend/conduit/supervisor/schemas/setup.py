# conduit/supervisor/schemas/setup.py
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

# Spec §8 Supervisor SLA/ladder CONFIG — the merged ``issue_code`` schema
# idiom VERBATIM: ``extra="forbid"`` on every model, plain Create / Patch
# (all-optional) / Out (``from_attributes``). Coherence (tier in P1-P4,
# seconds > 0, n_cycle_bound > 0) is enforced in the service exactly the
# way ``issue_codes._validate`` enforces its enums — NOT in pydantic — so
# an incoherent value is a clean 422 ``ValidationError`` (D31 "trusts
# well-formed config": only the spec-stated / CHECK-backed rules).


class SLAPresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # property_id is resolved server-side (single-property v1, AD9) — never
    # an operator input; mirrors sections/rosters (`_property_id`).
    tier: str
    accept_window_seconds: int
    fulfilment_sla_seconds: int
    supervisor_sla_seconds: int


class SLAPresetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier: str | None = None
    accept_window_seconds: int | None = None
    fulfilment_sla_seconds: int | None = None
    supervisor_sla_seconds: int | None = None
    status: str | None = None


class SLAPresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    property_id: uuid.UUID
    tier: str
    accept_window_seconds: int
    fulfilment_sla_seconds: int
    supervisor_sla_seconds: int
    status: str
    created_at: dt.datetime


class EscalationLadderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # property_id resolved server-side (single-property v1, AD9).
    duty_manager_account_id: uuid.UUID
    n_cycle_bound: int


class EscalationLadderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duty_manager_account_id: uuid.UUID | None = None
    n_cycle_bound: int | None = None
    status: str | None = None


class EscalationLadderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    property_id: uuid.UUID
    duty_manager_account_id: uuid.UUID
    n_cycle_bound: int
    status: str
    created_at: dt.datetime
