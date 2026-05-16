import datetime as dt
import uuid

import pytest

from conduit.shared.domain.availability import (
    current_window,
    effective_available,
    on_shift,
)


class _Roster:
    def __init__(self, start, end, status="active"):
        self.id = uuid.uuid4()
        self.shift_start, self.shift_end, self.status = start, end, status


class _Assignment:
    def __init__(self, roster, status="active"):
        self.roster = roster
        self.status = status


class _Profile:
    def __init__(self, presence="working", set_at=None, status="active"):
        self.presence, self.presence_set_at, self.status = (
            presence, set_at, status,
        )


UTC = dt.UTC
START = dt.datetime(2026, 5, 16, 8, 0, tzinfo=UTC)
END = dt.datetime(2026, 5, 16, 16, 0, tzinfo=UTC)
MID = dt.datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
BEFORE = dt.datetime(2026, 5, 16, 6, 0, tzinfo=UTC)


def _assignments(status="active", rstatus="active"):
    return [_Assignment(_Roster(START, END, rstatus), status)]


@pytest.mark.parametrize(
    "now,presence,set_at,prof_status,asg_status,expected",
    [
        # off-shift -> never available
        (BEFORE, "working", None, "active", "active", False),
        # on-shift, never toggled -> working default (D39-literal)
        (MID, "working", None, "active", "active", True),
        # on-shift, on_break set this window -> unavailable
        (MID, "on_break", MID, "active", "active", False),
        (MID, "off", MID, "active", "active", False),
        # on-shift, on_break but set BEFORE this window -> ignored => available
        (MID, "on_break", BEFORE, "active", "active", True),
        # on-shift, working, disabled profile -> unavailable
        (MID, "working", None, "disabled", "active", False),
        # on-shift but assignment disabled -> not on shift => unavailable
        (MID, "working", None, "active", "disabled", False),
        # boundary: exactly shift_start -> on shift (half-open [start,end))
        (START, "working", None, "active", "active", True),
        # boundary: exactly shift_end -> NOT on shift
        (END, "working", None, "active", "active", False),
        # boundary: presence_set_at == shift_start (in window) -> counts
        (MID, "off", START, "active", "active", False),
        # boundary: presence_set_at == shift_end (NOT in [start,end)) -> ignored
        (MID, "off", END, "active", "active", True),
    ],
)
def test_effective_available(
    now, presence, set_at, prof_status, asg_status, expected
):
    asgs = _assignments(asg_status)
    prof = _Profile(presence, set_at, prof_status)
    assert effective_available(prof, asgs, now) is expected


def test_current_window_and_on_shift():
    asgs = _assignments()
    assert on_shift(asgs, MID) is True
    assert on_shift(asgs, BEFORE) is False
    assert current_window(asgs, MID) is asgs[0].roster
    assert current_window(asgs, BEFORE) is None
