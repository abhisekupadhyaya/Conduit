"""Setup / configuration: the structure the runtime runs on.

Sections + room→section, per-shift rosters (D12/D18), issue-code catalog
(D34), SLA presets (D15), escalation ladder + duty manager (D21), KB (D26),
guest provisioning + stays (D3a/D29/D32). Config is data, not schema — these
are row edits, never migrations.

Spec §8 "Supervisor SLA/ladder CONFIG": ``GET|POST|PATCH
/supervisor/sla-presets`` and ``/supervisor/escalation-ladder`` — CONFIG
CRUD, disable-not-delete. This mirrors the merged ``issue_codes`` API idiom
VERBATIM: the ``_sup`` role gate, ``POST → 201`` returning the row, ``PATCH``
(disables via ``status='disabled'`` — there is NO delete handler, so any
``DELETE`` is a framework 405), the service raising ``ConflictError`` (409,
duplicate ACTIVE) / ``ValidationError`` (422, incoherent) / ``NotFoundError``
(404), and ``commit`` at the edge (reads never commit). The router is
composed ADDITIVELY in ``supervisor/api/__init__`` on the disjoint prefixes
``/supervisor/sla-presets`` + ``/supervisor/escalation-ladder`` — no E3/E4
or other CONFIG path is shadowed.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.shared.models.property import Property
from conduit.supervisor.schemas.setup import (
    EscalationLadderCreate,
    EscalationLadderOut,
    EscalationLadderPatch,
    SLAPresetCreate,
    SLAPresetOut,
    SLAPresetPatch,
)
from conduit.supervisor.services import setup as svc

_sup = require_roles("supervisor", "duty_manager")


async def _property_id(s: AsyncSession):
    """Single-property v1 (AD9): the property is resolved server-side, never
    an operator input — identical to ``binding._property_id`` /
    ``rosters._property_id``. Keeps the four CONFIG surfaces consistent."""
    return (await s.execute(select(Property.id))).scalars().first()


# The pre-existing setup-config placeholder (kept verbatim so the merged
# ``/supervisor/setup`` surface is unchanged).
router = APIRouter(prefix="/setup", tags=["supervisor-setup"])


@router.get("")
async def get_config(actor: Actor = Depends(_sup)) -> dict[str, str]:
    raise NotImplementedError


# --- SLA/ladder CONFIG CRUD (disjoint prefixes, additive) -----------------
setup_router = APIRouter(tags=["supervisor-setup"])


@setup_router.get("/sla-presets", response_model=list[SLAPresetOut])
async def list_presets(status: str | None = None,
                       actor: Actor = Depends(_sup),
                       s: AsyncSession = Depends(db_session)):
    return await svc.list_presets(s, status=status)


@setup_router.post("/sla-presets", response_model=SLAPresetOut,
                    status_code=201)
async def create_preset(body: SLAPresetCreate, actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    obj = await svc.create_preset(s, actor=actor,
                                  property_id=await _property_id(s),
                                  **body.model_dump())
    await s.commit()
    return obj


@setup_router.patch("/sla-presets/{preset_id}", response_model=SLAPresetOut)
async def patch_preset(preset_id: uuid.UUID, body: SLAPresetPatch,
                       actor: Actor = Depends(_sup),
                       s: AsyncSession = Depends(db_session)):
    obj = await svc.update_preset(s, preset_id, actor=actor,
                                  **body.model_dump(exclude_unset=True))
    await s.commit()
    return obj


@setup_router.get("/escalation-ladder",
                  response_model=list[EscalationLadderOut])
async def list_ladders(status: str | None = None,
                       actor: Actor = Depends(_sup),
                       s: AsyncSession = Depends(db_session)):
    return await svc.list_ladders(s, status=status)


@setup_router.post("/escalation-ladder",
                   response_model=EscalationLadderOut, status_code=201)
async def create_ladder(body: EscalationLadderCreate,
                         actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    obj = await svc.create_ladder(s, actor=actor,
                                  property_id=await _property_id(s),
                                  **body.model_dump())
    await s.commit()
    return obj


@setup_router.patch("/escalation-ladder/{ladder_id}",
                    response_model=EscalationLadderOut)
async def patch_ladder(ladder_id: uuid.UUID, body: EscalationLadderPatch,
                       actor: Actor = Depends(_sup),
                       s: AsyncSession = Depends(db_session)):
    obj = await svc.update_ladder(s, ladder_id, actor=actor,
                                  **body.model_dump(exclude_unset=True))
    await s.commit()
    return obj
