"""Login / logout / me — cookie session (AD8)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, current_actor, db_session
from conduit.core.security import (
    clear_session_cookie,
    issue_token,
    set_session_cookie,
)
from conduit.public.schemas.auth import AuthUser, LoginIn, SelfUpdateIn
from conduit.public.services import auth as svc

router = APIRouter(prefix="/auth", tags=["public-auth"])


@router.post("/login", response_model=AuthUser)
async def login(body: LoginIn, response: Response,
                s: AsyncSession = Depends(db_session)) -> AuthUser:
    acc = await svc.authenticate(s, body.username, body.password)
    set_session_cookie(response, issue_token(subject=str(acc.id), role=acc.role))
    return AuthUser.model_validate(acc)


@router.post("/logout", status_code=204)
async def logout(response: Response,
                 actor: Actor = Depends(current_actor)) -> None:
    # Auth-required so the auth-coverage guard's PUBLIC allowlist stays
    # {health, login}; an unauthenticated POST returns 401.
    clear_session_cookie(response)


@router.get("/me", response_model=AuthUser)
async def me(actor: Actor = Depends(current_actor),
             s: AsyncSession = Depends(db_session)) -> AuthUser:
    acc = await svc.current_account(s, actor.id)
    base = AuthUser.model_validate(acc).model_dump()
    amb = await svc.resolve_ambient(s, actor) or {}
    return AuthUser(**{**base, **amb})


@router.patch("/me", response_model=AuthUser)
async def patch_me(body: SelfUpdateIn, actor: Actor = Depends(current_actor),
                   s: AsyncSession = Depends(db_session)) -> AuthUser:
    acc = await svc.current_account(s, actor.id)
    acc = await svc.update_self(
        s, acc, status_change=None, display_name=body.display_name,
        current_password=body.current_password, new_password=body.new_password)
    await s.commit()
    return AuthUser.model_validate(acc)
