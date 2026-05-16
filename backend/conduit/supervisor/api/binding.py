# conduit/supervisor/api/binding.py
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.deps import Actor, db_session, require_roles
from conduit.shared.models.account import Account
from conduit.shared.models.property import Property
from conduit.supervisor.dal import rooms as rdal, sections as sdal
from conduit.supervisor.schemas.binding import (
    RelocateIn, RoomCreate, RoomOut, RoomUpdate, SectionCreate, SectionOut,
    StayCreate, StayOut, StayUpdate,
)
from conduit.supervisor.services import (
    rooms as rsvc, sections as ssvc, stays as stsvc,
)

router = APIRouter(tags=["supervisor-binding"])
_sup = require_roles("supervisor", "duty_manager")


async def _property_id(s: AsyncSession) -> uuid.UUID:
    return (await s.execute(select(Property.id))).scalars().first()


def _section_out(sec, count) -> SectionOut:
    return SectionOut(id=sec.id, label=sec.label, room_count=count,
                      created_at=sec.created_at)


async def _room_out(s, r) -> RoomOut:
    sec = await sdal.get_section(s, r.section_id)
    return RoomOut(id=r.id, label=r.label, section_id=r.section_id,
                   section_label=sec.label, created_at=r.created_at)


async def _stay_out(s, st) -> StayOut:
    room = await rdal.get_room(s, st.room_id)
    sec = await sdal.get_section(s, room.section_id)
    guest = await s.get(Account, st.guest_account_id)
    return StayOut(
        id=st.id, guest_account_id=st.guest_account_id,
        guest_display_name=guest.display_name,
        room_id=room.id, room_label=room.label,
        section_id=sec.id, section_label=sec.label,
        check_in=st.check_in, check_out=st.check_out,
        status=st.status, created_at=st.created_at)


@router.get("/sections", response_model=list[SectionOut])
async def list_sections(actor: Actor = Depends(_sup),
                        s: AsyncSession = Depends(db_session)):
    return [_section_out(sec, c) for sec, c in await ssvc.list_sections(s)]


@router.post("/sections", response_model=SectionOut, status_code=201)
async def create_section(body: SectionCreate, actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    sec = await ssvc.create_section(s, await _property_id(s),
                                    body.label, actor=actor)
    await s.commit()
    return _section_out(sec, 0)


@router.patch("/sections/{section_id}", response_model=SectionOut)
async def rename_section(section_id: uuid.UUID, body: SectionCreate,
                         actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    sec = await ssvc.rename_section(s, section_id, body.label, actor=actor)
    await s.commit()
    counts = {x.id: c for x, c in await ssvc.list_sections(s)}
    return _section_out(sec, counts.get(sec.id, 0))


@router.get("/rooms", response_model=list[RoomOut])
async def list_rooms(section_id: uuid.UUID | None = None,
                     actor: Actor = Depends(_sup),
                     s: AsyncSession = Depends(db_session)):
    return [await _room_out(s, r)
            for r in await rsvc.list_rooms(s, section_id)]


@router.post("/rooms", response_model=RoomOut, status_code=201)
async def create_room(body: RoomCreate, actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    r = await rsvc.create_room(s, body.label, body.section_id, actor=actor)
    await s.commit()
    return await _room_out(s, r)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(room_id: uuid.UUID, body: RoomUpdate,
                      actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    r = await rsvc.update_room(s, room_id, label=body.label,
                               section_id=body.section_id, actor=actor)
    await s.commit()
    return await _room_out(s, r)


@router.get("/stays", response_model=list[StayOut])
async def list_stays(status: str | None = None,
                     guest_id: uuid.UUID | None = None,
                     actor: Actor = Depends(_sup),
                     s: AsyncSession = Depends(db_session)):
    return [await _stay_out(s, st)
            for st in await stsvc.list_stays(s, status=status,
                                             guest_id=guest_id)]


@router.post("/stays", response_model=StayOut, status_code=201)
async def create_stay(body: StayCreate, actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    st = await stsvc.create_stay(s, body.guest_account_id, body.room_id,
                                 body.check_in, body.check_out, actor=actor)
    await s.commit()
    return await _stay_out(s, st)


@router.patch("/stays/{stay_id}", response_model=StayOut)
async def update_stay(stay_id: uuid.UUID, body: StayUpdate,
                      actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    st = await stsvc.update_stay(s, stay_id, check_in=body.check_in,
                                 check_out=body.check_out, actor=actor)
    await s.commit()
    return await _stay_out(s, st)


@router.post("/stays/{stay_id}/relocate", response_model=StayOut)
async def relocate(stay_id: uuid.UUID, body: RelocateIn,
                   actor: Actor = Depends(_sup),
                   s: AsyncSession = Depends(db_session)):
    st = await stsvc.relocate_stay(s, stay_id, body.new_room_id, actor=actor)
    await s.commit()
    return await _stay_out(s, st)


@router.post("/stays/{stay_id}/checkout", response_model=StayOut)
async def checkout(stay_id: uuid.UUID, actor: Actor = Depends(_sup),
                  s: AsyncSession = Depends(db_session)):
    st = await stsvc.checkout_stay(s, stay_id, actor=actor)
    await s.commit()
    return await _stay_out(s, st)
