# conduit/supervisor/schemas/staff.py
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class ProfileOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_class: str
    presence: str
    status: str


class StaffOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    display_name: str
    profile: ProfileOut | None
    skills: list[str]


class CreateProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_class: str


class PatchProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_class: str | None = None
    status: str | None = None


class SetSkillsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skills: list[str]
