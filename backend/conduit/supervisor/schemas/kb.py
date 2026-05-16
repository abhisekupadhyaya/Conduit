# conduit/supervisor/schemas/kb.py
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class KBEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str
    content: str


class KBEntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str | None = None
    content: str | None = None
    status: str | None = None


class KBEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    topic: str
    content: str
    status: str
    created_at: dt.datetime
