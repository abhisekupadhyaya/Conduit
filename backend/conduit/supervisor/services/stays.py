# conduit/supervisor/services/stays.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import ConflictError, NotFoundError, ValidationError
from conduit.shared.models.account import Account
from conduit.supervisor.dal import stays as dal, rooms as rdal, events as edal


def _actor_id(actor) -> uuid.UUID | None:
    aid = getattr(actor, "id", None)
    return uuid.UUID(str(aid)) if aid is not None else None


async def list_stays(s: AsyncSession, status=None, guest_id=None):
    return await dal.list_stays(s, status=status, guest_id=guest_id)


async def _require_guest(s, guest_account_id):
    g = await s.get(Account, guest_account_id)
    if g is None or g.role != "guest" or g.status != "active":
        raise ValidationError("guest account invalid")


async def _require_room(s, room_id):
    if await rdal.get_room(s, room_id) is None:
        raise ValidationError("room does not exist")


async def create_stay(s: AsyncSession, guest_account_id: uuid.UUID,
                        room_id: uuid.UUID, check_in: datetime,
                        check_out: datetime, *, actor):
    await _require_guest(s, guest_account_id)
    await _require_room(s, room_id)
    if await dal.get_active_stay_for_guest(s, guest_account_id) is not None:
        raise ConflictError("guest already has an active stay")
    st = await dal.insert_stay(s, guest_account_id, room_id,
                                check_in, check_out)
    await s.flush()
    ev = await edal.insert_event(s, type="stay_created",
                                  actor_account_id=_actor_id(actor))
    await s.flush()
    await edal.insert_stay_created(s, ev.id, st.id)
    return st


async def update_stay(s: AsyncSession, stay_id: uuid.UUID, *,
                       check_in: datetime | None = None,
                       check_out: datetime | None = None, actor):
    st = await dal.get_stay(s, stay_id)
    if st is None:
        raise NotFoundError("stay not found")
    return await dal.update_stay_fields(s, st, check_in=check_in,
                                         check_out=check_out)


async def relocate_stay(s: AsyncSession, stay_id: uuid.UUID,
                          new_room_id: uuid.UUID, *, actor):
    st = await dal.get_stay(s, stay_id)
    if st is None:
        raise NotFoundError("stay not found")
    if st.status != "active":
        raise ConflictError("stay is not active")
    await _require_room(s, new_room_id)
    if st.room_id == new_room_id:
        raise ConflictError("already in that room")
    from_room = st.room_id
    await dal.set_stay_room(s, st, new_room_id)
    await s.flush()
    ev = await edal.insert_event(s, type="guest_relocated",
                                  actor_account_id=_actor_id(actor))
    await s.flush()
    await edal.insert_guest_relocated(s, ev.id, st.id,
                                       from_room, new_room_id)
    return st


async def checkout_stay(s: AsyncSession, stay_id: uuid.UUID, *, actor):
    st = await dal.get_stay(s, stay_id)
    if st is None:
        raise NotFoundError("stay not found")
    if st.status != "active":
        raise ConflictError("stay is not active")
    await dal.set_stay_status(s, st, "ended")
    await s.flush()
    ev = await edal.insert_event(s, type="stay_ended",
                                  actor_account_id=_actor_id(actor))
    await s.flush()
    await edal.insert_stay_ended(s, ev.id, st.id)
    return st
