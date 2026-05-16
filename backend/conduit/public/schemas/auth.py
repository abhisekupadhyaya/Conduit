from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class LoginIn(BaseModel):
    username: str
    password: str


class AuthUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    username: str
    display_name: str


class SelfUpdateIn(BaseModel):
    display_name: str | None = None
    current_password: str | None = None
    new_password: str | None = None
