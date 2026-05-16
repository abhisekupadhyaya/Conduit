from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class AccountCreateIn(BaseModel):
    role: str
    username: str
    display_name: str
    password: str


class AccountUpdateIn(BaseModel):
    display_name: str | None = None
    status: str | None = None
    password: str | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    username: str
    display_name: str
    status: str
    created_at: dt.datetime
