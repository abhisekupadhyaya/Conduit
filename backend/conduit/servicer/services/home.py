# conduit/servicer/services/home.py
"""Servicer home — one composed DERIVED read. No event, no commit.

Spec §4 "Predicate home": this calls the SAME pure
``shared.domain.availability`` functions next slice's routing will call — the
rule is never re-derived here. §4 "Time source": business ``now`` comes from
``conduit.core.clock.now()`` (the single freezegun-controllable call site).

Un-profiled servicer (provisioned, not yet profiled — a first-class state per
§4 "Profile verb shape"): return a sensible home rather than crash —
``profile`` null, ``presence`` the default ``"working"`` literal,
``presence_locked`` driven purely by the roster window, ``effective_available``
False (no active profile ⇒ not available, consistent with the
``effective_available`` predicate's ``profile.status`` gate).
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core import clock
from conduit.core.deps import Actor
from conduit.servicer.dal import self as dal
from conduit.shared.domain import availability


def _shift_dict(s_assignment, roster, section_label: str | None) -> dict:
    return {
        "shift_start": roster.shift_start,
        "shift_end": roster.shift_end,
        "section_label": section_label,
        "role": s_assignment.assignment,
    }


async def get_home(s: AsyncSession, actor: Actor) -> dict:
    account_id = uuid.UUID(str(actor.id))
    profile = await dal.get_profile(s, account_id)
    skills = await dal.get_skills(s, account_id)
    assignments = await dal.get_assignments(s, account_id)

    now = clock.now()
    w = availability.current_window(assignments, now)

    current_shift: dict | None = None
    if w is not None:
        cur = next(
            a
            for a in assignments
            if a.status == "active"
            and a.roster is not None
            and a.roster.id == w.id
        )
        current_shift = _shift_dict(
            cur, w, await dal.get_section_label(s, cur.section_id)
        )

    # Soonest FUTURE active window among this servicer's assignments.
    future = [
        a
        for a in assignments
        if a.status == "active"
        and a.roster is not None
        and a.roster.status == "active"
        and a.roster.shift_start > now
    ]
    next_shift: dict | None = None
    if future:
        nxt = min(future, key=lambda a: a.roster.shift_start)
        next_shift = _shift_dict(
            nxt,
            nxt.roster,
            await dal.get_section_label(s, nxt.section_id),
        )

    presence_locked = w is None
    if profile is None:
        return {
            "profile": None,
            "skills": skills,
            "current_shift": current_shift,
            "next_shift": next_shift,
            "presence": "working",
            "presence_locked": presence_locked,
            "effective_available": False,
        }

    return {
        "profile": {
            "class": profile.staff_class,
            "skills": skills,
            "status": profile.status,
        },
        "skills": skills,
        "current_shift": current_shift,
        "next_shift": next_shift,
        "presence": profile.presence,
        "presence_locked": presence_locked,
        "effective_available": availability.effective_available(
            profile, assignments, now
        ),
    }
