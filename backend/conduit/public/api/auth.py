"""Login (D3a) — supervisor-provisioned credentials, app-managed JWT (AD8)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["public-auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    role: str


@router.post("/login", response_model=LoginOut)
async def login(_: LoginIn) -> LoginOut:
    # Verify credentials against the account store, then issue_token(...).
    # Scaffolding: not implemented until the account model lands.
    raise NotImplementedError
