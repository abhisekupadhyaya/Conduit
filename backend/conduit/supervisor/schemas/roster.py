# conduit/supervisor/schemas/roster.py
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class RosterOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    shift_start: dt.datetime
    shift_end: dt.datetime
    status: str


class CreateRosterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shift_start: dt.datetime
    shift_end: dt.datetime


class PatchRosterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shift_start: dt.datetime | None = None
    shift_end: dt.datetime | None = None
    status: str | None = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    roster_id: uuid.UUID
    account_id: uuid.UUID
    section_id: uuid.UUID | None
    assignment: str
    status: str


class CreateAssignmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    section_id: uuid.UUID | None = None
    assignment: str


class PatchAssignmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_id: uuid.UUID | None = None
    assignment: str | None = None
    status: str | None = None
