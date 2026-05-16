# conduit/supervisor/services/staff.py
"""Supervisor Staff service — guards + events + flush; reads compose DAL.

Events seam (spec §4 "Events seam (two halves)"): config mutations do NOT
go through ``lifecycle.transition`` (the child state machine). They append
to the merged ``shared/events`` log directly, using the EXACT call shape the
merged ``conduit.shared.events.writer`` uses internally (``Event(...)`` ->
``s.add`` -> ``await s.flush()`` -> add the typed per-event detail row keyed
by ``event_id``). There is no staffing helper in the writer and the writer
module is out of scope to modify, so the established shape is replicated
here verbatim against the Task-2 ``EventStaff*`` detail classes.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core import clock
from conduit.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from conduit.shared.domain import availability
from conduit.shared.models import (
    Event,
    EventStaffProfileCreated,
    EventStaffProfileUpdated,
    EventStaffSkillsSet,
    StaffProfile,
)
from conduit.supervisor.dal import staff as dal


async def _derive(
    s: AsyncSession, account_id: uuid.UUID, p: StaffProfile | None, now: dt.datetime
) -> tuple[bool, bool]:
    """Task 5b (user-authorized scope add): REAL derived availability via the
    SAME pure ``shared.domain.availability`` predicate the servicer home
    reads — single source of the rule, not re-derived here. ``on_shift`` is
    profile-independent (assignments + window only). The
    ``if p is None: return on_shift, False`` guard below is REQUIRED, not
    merely defensive: ``availability.effective_available`` is not None-safe —
    when a current window exists it dereferences ``profile.status`` and would
    raise ``AttributeError`` on a None profile. Do not remove the guard.
    Reads only: no flush, no event."""
    assignments = await dal.get_assignments_with_roster(s, account_id)
    on_shift = availability.on_shift(assignments, now)
    if p is None:
        return on_shift, False
    return on_shift, availability.effective_available(p, assignments, now)


async def list_staff(s: AsyncSession) -> list[dict]:
    now = clock.now()
    out: list[dict] = []
    for acc in await dal.list_servicer_accounts(s):
        p = await dal.get_profile(s, acc.id)
        on_shift, eff = await _derive(s, acc.id, p, now)
        out.append(
            {
                "account_id": acc.id,
                "display_name": acc.display_name,
                "profile": None
                if p is None
                else {
                    "staff_class": p.staff_class,
                    "presence": p.presence,
                    "status": p.status,
                },
                "skills": await dal.get_skills(s, acc.id),
                "on_shift": on_shift,
                "effective_available": eff,
            }
        )
    return out


async def get_staff(s: AsyncSession, account_id: uuid.UUID) -> dict:
    acc = await dal.get_account(s, account_id)
    if acc is None or acc.role != "servicer":
        raise NotFoundError("servicer account not found")
    p = await dal.get_profile(s, account_id)
    now = clock.now()
    on_shift, eff = await _derive(s, account_id, p, now)
    return {
        "account_id": acc.id,
        "display_name": acc.display_name,
        "profile": None
        if p is None
        else {
            "staff_class": p.staff_class,
            "presence": p.presence,
            "status": p.status,
        },
        "skills": await dal.get_skills(s, account_id),
        "on_shift": on_shift,
        "effective_available": eff,
    }


async def create_profile(
    s: AsyncSession,
    actor_id: uuid.UUID | None,
    account_id: uuid.UUID,
    staff_class: str,
) -> StaffProfile:
    acc = await dal.get_account(s, account_id)
    if acc is None:
        raise NotFoundError("account not found")
    if acc.role != "servicer":
        raise ValidationError("account is not a servicer")
    if await dal.get_profile(s, account_id) is not None:
        raise ConflictError("staff profile already exists")
    p = dal.add_profile(s, account_id, staff_class)
    e = Event(type="staff_profile_created", actor_account_id=actor_id)
    s.add(e)
    await s.flush()
    s.add(EventStaffProfileCreated(event_id=e.id, account_id=account_id))
    await s.flush()
    return p


async def patch_profile(
    s: AsyncSession,
    actor_id: uuid.UUID | None,
    account_id: uuid.UUID,
    staff_class: str | None,
    status: str | None,
) -> StaffProfile:
    p = await dal.get_profile(s, account_id)
    if p is None:
        raise NotFoundError("staff profile not found")
    if staff_class is not None:
        p.staff_class = staff_class
    if status is not None:
        p.status = status
    s.add(p)
    e = Event(type="staff_profile_updated", actor_account_id=actor_id)
    s.add(e)
    await s.flush()
    s.add(EventStaffProfileUpdated(event_id=e.id, account_id=account_id))
    await s.flush()
    return p


async def set_skills(
    s: AsyncSession,
    actor_id: uuid.UUID | None,
    account_id: uuid.UUID,
    skills: list[str],
) -> None:
    if await dal.get_profile(s, account_id) is None:
        raise NotFoundError("staff profile not found")
    await dal.replace_skills(s, account_id, skills)
    e = Event(type="staff_skills_set", actor_account_id=actor_id)
    s.add(e)
    await s.flush()
    s.add(EventStaffSkillsSet(event_id=e.id, account_id=account_id))
    await s.flush()
