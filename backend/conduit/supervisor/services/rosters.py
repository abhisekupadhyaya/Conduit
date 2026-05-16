# conduit/supervisor/services/rosters.py
"""Supervisor Rosters service — guards + events + flush; reads compose DAL.

Mirrors Task 5's ``services/staff.py`` EXACTLY: domain-error guards, then the
``shared/events`` append-only writer's internal call shape replicated
verbatim (``Event(...)`` -> ``s.add`` -> ``await s.flush()`` -> typed detail
row keyed by ``event_id`` -> trailing ``await s.flush()`` for pre-commit test
visibility). Config mutations do NOT go through ``lifecycle.transition`` (the
child state machine) — spec §4 "Events seam (two halves)".

The D12/D18 split (spec §4 "Assignment model", §6):
- ``owner``/``backup`` without ``section_id`` -> ``ValidationError`` (clean
  422; the DB CHECK ``ck_assignment_owner_needs_section`` also enforces it).
- engineering-class account WITH ``section_id`` -> ``ValidationError`` (D18:
  engineering is skill-matched, not section-pooled — a cross-table rule, not
  a CHECK).
- duplicate active owner for ``(roster, section)`` -> the partial-unique
  index ``uq_active_owner_per_section`` raises ``IntegrityError`` on flush ->
  caught -> ``ConflictError`` (409).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from conduit.shared.models import (
    Event,
    EventAssignmentCreated,
    EventAssignmentUpdated,
    EventRosterCreated,
    EventRosterUpdated,
    Roster,
    RosterAssignment,
)
from conduit.supervisor.dal import rosters as dal


async def list_rosters(
    s: AsyncSession,
    status: str | None = None,
    active_at: dt.datetime | None = None,
) -> list[Roster]:
    return await dal.list_rosters(s, status=status, active_at=active_at)


async def get_roster(s: AsyncSession, roster_id: uuid.UUID) -> Roster:
    r = await dal.get_roster(s, roster_id)
    if r is None:
        raise NotFoundError("roster not found")
    return r


async def create_roster(
    s: AsyncSession,
    actor_id: uuid.UUID | None,
    property_id: uuid.UUID,
    shift_start: dt.datetime,
    shift_end: dt.datetime,
) -> Roster:
    if shift_end <= shift_start:
        raise ValidationError("shift_end must be after shift_start")
    r = dal.add_roster(s, property_id, shift_start, shift_end)
    e = Event(type="roster_created", actor_account_id=actor_id)
    s.add(e)
    await s.flush()
    s.add(EventRosterCreated(event_id=e.id, roster_id=r.id))
    await s.flush()
    return r


async def update_roster(
    s: AsyncSession,
    actor_id: uuid.UUID | None,
    roster_id: uuid.UUID,
    shift_start: dt.datetime | None,
    shift_end: dt.datetime | None,
    status: str | None,
) -> Roster:
    r = await dal.get_roster(s, roster_id)
    if r is None:
        raise NotFoundError("roster not found")
    if shift_start is not None:
        r.shift_start = shift_start
    if shift_end is not None:
        r.shift_end = shift_end
    if r.shift_end <= r.shift_start:
        raise ValidationError("shift_end must be after shift_start")
    if status is not None:
        r.status = status
    s.add(r)
    e = Event(type="roster_updated", actor_account_id=actor_id)
    s.add(e)
    await s.flush()
    s.add(EventRosterUpdated(event_id=e.id, roster_id=r.id))
    await s.flush()
    return r


async def list_assignments(
    s: AsyncSession, roster_id: uuid.UUID
) -> list[RosterAssignment]:
    await get_roster(s, roster_id)  # 404 if the roster does not exist
    return await dal.list_assignments(s, roster_id)


async def create_assignment(
    s: AsyncSession,
    actor_id: uuid.UUID | None,
    roster_id: uuid.UUID,
    account_id: uuid.UUID,
    section_id: uuid.UUID | None,
    assignment: str,
) -> RosterAssignment:
    await get_roster(s, roster_id)  # 404 if the roster does not exist
    acc = await dal.get_account(s, account_id)
    if acc is None or acc.role != "servicer":
        raise ValidationError("account is not a servicer")
    profile = await dal.get_profile(s, account_id)
    if profile is None or profile.status != "active":
        raise ValidationError("account has no active staff profile")
    # D18: engineering is skill-matched, not section-pooled.
    if profile.staff_class == "engineering" and section_id is not None:
        raise ValidationError(
            "engineering is skill-matched, not section-pooled"
        )
    # D12: an owner/backup is a positional accountability — needs a post.
    if assignment in ("owner", "backup") and section_id is None:
        raise ValidationError(
            "owner/backup assignment requires a section_id"
        )
    a = dal.add_assignment(
        s, roster_id, account_id, section_id, assignment
    )
    try:
        await s.flush()
    except IntegrityError as exc:
        # The partial-unique uq_active_owner_per_section: one active owner
        # per (roster, section) per window (D12).
        raise ConflictError(
            "section already has an active owner"
        ) from exc
    e = Event(type="assignment_created", actor_account_id=actor_id)
    s.add(e)
    await s.flush()
    s.add(EventAssignmentCreated(event_id=e.id, assignment_id=a.id))
    await s.flush()
    return a


async def update_assignment(
    s: AsyncSession,
    actor_id: uuid.UUID | None,
    roster_id: uuid.UUID,
    assignment_id: uuid.UUID,
    section_id: uuid.UUID | None,
    assignment: str | None,
    status: str | None,
) -> RosterAssignment:
    await get_roster(s, roster_id)  # 404 if the roster does not exist
    a = await dal.get_assignment(s, assignment_id)
    if a is None or a.roster_id != roster_id:
        raise NotFoundError("assignment not found")
    if section_id is not None:
        a.section_id = section_id
    if assignment is not None:
        a.assignment = assignment
    if status is not None:
        a.status = status
    s.add(a)
    e = Event(type="assignment_updated", actor_account_id=actor_id)
    s.add(e)
    await s.flush()
    s.add(EventAssignmentUpdated(event_id=e.id, assignment_id=a.id))
    await s.flush()
    return a
