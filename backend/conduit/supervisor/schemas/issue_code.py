# conduit/supervisor/schemas/issue_code.py
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class IssueCodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # rejects is_reservation_mutation
    code: str
    label: str
    department: str
    fulfilment_mode: str
    routing_model: str
    intent_kind: str = "service"


class IssueCodePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = None
    label: str | None = None
    department: str | None = None
    fulfilment_mode: str | None = None
    routing_model: str | None = None
    intent_kind: str | None = None
    status: str | None = None


class IssueCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    code: str
    label: str
    department: str
    fulfilment_mode: str
    routing_model: str
    intent_kind: str
    is_reservation_mutation: bool   # display-only
    status: str
    created_at: dt.datetime
