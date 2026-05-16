from conduit.shared.models import (
    StaffProfile, StaffSkill, Roster, RosterAssignment, Event,
    EventStaffProfileCreated, EventStaffProfileUpdated, EventStaffSkillsSet,
    EventRosterCreated, EventRosterUpdated,
    EventAssignmentCreated, EventAssignmentUpdated, EventPresenceChanged,
)


def test_staffing_models_registered():
    assert StaffProfile.__tablename__ == "staff_profile"
    assert StaffSkill.__tablename__ == "staff_skill"
    assert Roster.__tablename__ == "roster"
    assert RosterAssignment.__tablename__ == "roster_assignment"
    assert EventPresenceChanged.__tablename__ == "event_presence_changed"
    assert EventAssignmentCreated.__tablename__ == "event_assignment_created"


import subprocess
import sys
from pathlib import Path

def test_migration_round_trip():
    # up to head, then one step down, then back up — must not error.
    # Resolve the backend dir from this test file's location so the round-trip
    # runs from any worktree (inherited test hardcoded a sibling dev path).
    base = Path(__file__).resolve().parents[2]
    for args in (["upgrade", "head"], ["downgrade", "-1"], ["upgrade", "head"]):
        r = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=str(base), capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
