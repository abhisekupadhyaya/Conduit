# conduit/servicer/api/self.py
"""Servicer self API (spec §8 "Servicer — self").

Per-handler ``require_roles("servicer")`` gate (server-side regardless of
client). ``GET /servicer/home`` is a pure derived read — never commits.
``PUT /servicer/presence`` mutates: off-shift → 409 (the server lock,
raised in the service), edge ``await s.commit()`` on success only. No
``DELETE`` → FastAPI 405 (the cross-slice invariant). ORM/derived → schema
mapping happens at THIS layer only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.servicer.schemas.home import ServicerHomeOut, SetPresenceIn
from conduit.servicer.services import home as home_svc
from conduit.servicer.services import presence as presence_svc

router = APIRouter(tags=["servicer-self"])
_svc = require_roles("servicer")


@router.get("/home", response_model=ServicerHomeOut)
async def get_home(
    actor: Actor = Depends(_svc),
    s: AsyncSession = Depends(db_session),
):
    return ServicerHomeOut.model_validate(await home_svc.get_home(s, actor))


@router.put("/presence", response_model=ServicerHomeOut)
async def put_presence(
    body: SetPresenceIn,
    actor: Actor = Depends(_svc),
    s: AsyncSession = Depends(db_session),
):
    await presence_svc.set_presence(s, actor, body.presence)
    await s.commit()
    return ServicerHomeOut.model_validate(await home_svc.get_home(s, actor))
