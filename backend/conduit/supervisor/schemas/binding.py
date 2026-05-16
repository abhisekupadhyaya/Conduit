# conduit/supervisor/schemas/binding.py
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _B(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SectionCreate(_B):
    label: str


class SectionOut(_B):
    id: uuid.UUID
    label: str
    room_count: int
    created_at: datetime


class RoomCreate(_B):
    label: str
    section_id: uuid.UUID


class RoomUpdate(_B):
    label: str | None = None
    section_id: uuid.UUID | None = None


class RoomOut(_B):
    id: uuid.UUID
    label: str
    section_id: uuid.UUID
    section_label: str
    created_at: datetime


class StayCreate(_B):
    guest_account_id: uuid.UUID
    room_id: uuid.UUID
    check_in: datetime
    check_out: datetime


class StayUpdate(_B):
    check_in: datetime | None = None
    check_out: datetime | None = None


class RelocateIn(_B):
    new_room_id: uuid.UUID


class StayOut(_B):
    id: uuid.UUID
    guest_account_id: uuid.UUID
    guest_display_name: str
    room_id: uuid.UUID
    room_label: str
    section_id: uuid.UUID
    section_label: str
    check_in: datetime
    check_out: datetime
    status: str
    created_at: datetime
