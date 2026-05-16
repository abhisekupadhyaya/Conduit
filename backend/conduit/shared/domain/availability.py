# conduit/shared/domain/availability.py
"""Pure derived availability — no DB. The substrate routing consumes.

current_window/on_shift/effective_available take already-fetched rows
(assignments each carrying `.roster`, a profile) plus an explicit `now`.
The window is half-open: now in [shift_start, shift_end).
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Protocol


class _Roster(Protocol):
    shift_start: dt.datetime
    shift_end: dt.datetime
    status: str


class _Assignment(Protocol):
    roster: _Roster
    status: str


class _Profile(Protocol):
    presence: str
    presence_set_at: dt.datetime | None
    status: str


def current_window(
    assignments: Iterable[_Assignment], now: dt.datetime
) -> _Roster | None:
    for a in assignments:
        if a.status != "active":
            continue
        r = a.roster
        if r.status == "active" and r.shift_start <= now < r.shift_end:
            return r
    return None


def on_shift(assignments: Iterable[_Assignment], now: dt.datetime) -> bool:
    return current_window(assignments, now) is not None


def effective_available(
    profile: _Profile,
    assignments: Iterable[_Assignment],
    now: dt.datetime,
) -> bool:
    w = current_window(assignments, now)
    if w is None or profile.status != "active":
        return False
    if (
        profile.presence in ("on_break", "off")
        and profile.presence_set_at is not None
        and w.shift_start <= profile.presence_set_at < w.shift_end
    ):
        return False
    return True  # Working default (D39-literal)
