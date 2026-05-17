"""Exhaustive tests for the pure routing.select (Spec §7.1, D12/D18).

No DB, no clock — all inputs constructed; the REAL effective_available is
called (not mocked) with an explicit `now`, fed inputs that make it return
the booleans each case intends.
"""
import datetime as dt
import uuid

from conduit.shared.domain.routing import (
    Candidate,
    RoutingModel,
    Selection,
    select,
)

UTC = dt.UTC
START = dt.datetime(2026, 5, 16, 8, 0, tzinfo=UTC)
END = dt.datetime(2026, 5, 16, 16, 0, tzinfo=UTC)
MID = dt.datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
BEFORE = dt.datetime(2026, 5, 16, 6, 0, tzinfo=UTC)


class _Roster:
    def __init__(self, start=START, end=END, status="active"):
        self.id = uuid.uuid4()
        self.shift_start, self.shift_end, self.status = start, end, status


class _Assignment:
    def __init__(self, roster=None, status="active"):
        self.roster = roster if roster is not None else _Roster()
        self.status = status


class _Profile:
    def __init__(self, presence="working", set_at=None, status="active"):
        self.presence, self.presence_set_at, self.status = (
            presence, set_at, status,
        )


def _avail_assignments():
    """Inputs that make the REAL effective_available(...) return True at MID."""
    return [_Assignment(_Roster(START, END, "active"), "active")]


def _busy_assignments():
    """Off-shift roster -> REAL effective_available(...) returns False at MID."""
    return [_Assignment(_Roster(BEFORE, BEFORE, "active"), "active")]


def _cand(
    *,
    available=True,
    is_section_owner=False,
    in_zone=True,
    skills=(),
    active_load=0,
    priority_tier="P3",
):
    return Candidate(
        account_id=uuid.uuid4(),
        profile=_Profile(),
        assignments=_avail_assignments() if available else _busy_assignments(),
        skills=tuple(skills),
        active_load=active_load,
        is_section_owner=is_section_owner,
        in_zone=in_zone,
        priority_tier=priority_tier,
    )


# ---------------------------------------------------------------- D12 -------

def test_d12_owner_available_selected():
    owner = _cand(available=True, is_section_owner=True, in_zone=True)
    pool1 = _cand(available=True, in_zone=True)
    section_id = uuid.uuid4()
    sel = select(
        model=RoutingModel.SECTION_POOLED,
        candidates=[owner, pool1],
        now=MID,
        section_id=section_id,
    )
    assert isinstance(sel, Selection)
    assert sel.assigned_id == owner.account_id
    assert sel.accountable_id == owner.account_id
    assert sel.broadcast_pool == []
    assert sel.section_id == section_id
    assert sel.flag is False
    assert sel.flag_reason is None


def test_d12_owner_busy_broadcasts_pool_owner_stays_accountable():
    owner = _cand(available=False, is_section_owner=True, in_zone=True)
    in_pool_a = _cand(available=True, in_zone=True)
    in_pool_b = _cand(available=True, in_zone=True)
    out_of_zone = _cand(available=True, in_zone=False)
    busy_in_zone = _cand(available=False, in_zone=True)
    section_id = uuid.uuid4()
    sel = select(
        model=RoutingModel.SECTION_POOLED,
        candidates=[owner, in_pool_a, in_pool_b, out_of_zone, busy_in_zone],
        now=MID,
        section_id=section_id,
    )
    assert sel.assigned_id is None
    assert sel.accountable_id == owner.account_id  # owner stays accountable
    assert set(sel.broadcast_pool) == {
        in_pool_a.account_id,
        in_pool_b.account_id,
    }
    assert out_of_zone.account_id not in sel.broadcast_pool
    assert busy_in_zone.account_id not in sel.broadcast_pool
    assert sel.section_id == section_id
    assert sel.flag is False
    assert sel.flag_reason is None


def test_d12_owner_busy_no_pool_flags():
    owner = _cand(available=False, is_section_owner=True, in_zone=True)
    sel = select(
        model=RoutingModel.SECTION_POOLED,
        candidates=[owner],
        now=MID,
        section_id=uuid.uuid4(),
    )
    assert sel.assigned_id is None
    assert sel.accountable_id == owner.account_id
    assert sel.broadcast_pool == []
    assert sel.flag is True
    assert sel.flag_reason is not None


# ---------------------------------------------------------------- D18 -------

def test_d18_skill_match_least_loaded():
    matched_heavy = _cand(available=True, skills=["hvac"], active_load=5)
    matched_light = _cand(available=True, skills=["hvac"], active_load=1)
    matched_busy = _cand(available=False, skills=["hvac"], active_load=0)
    wrong_skill = _cand(available=True, skills=["plumbing"], active_load=0)
    sel = select(
        model=RoutingModel.SKILL_MATCHED,
        candidates=[matched_heavy, matched_light, matched_busy, wrong_skill],
        now=MID,
        required_skill="hvac",
    )
    assert sel.assigned_id == matched_light.account_id
    assert sel.accountable_id == matched_light.account_id
    assert sel.broadcast_pool == []
    assert sel.flag is False
    assert sel.flag_reason is None


def test_d18_load_tie_p1_preempts():
    p3 = _cand(
        available=True, skills=["hvac"], active_load=2, priority_tier="P3"
    )
    p1 = _cand(
        available=True, skills=["hvac"], active_load=2, priority_tier="P1"
    )
    p2 = _cand(
        available=True, skills=["hvac"], active_load=2, priority_tier="P2"
    )
    sel = select(
        model=RoutingModel.SKILL_MATCHED,
        candidates=[p3, p1, p2],
        now=MID,
        required_skill="hvac",
    )
    assert sel.assigned_id == p1.account_id
    assert sel.accountable_id == p1.account_id
    assert sel.queue_position == 0
    assert sel.flag is False


def test_no_candidate_flags():
    sel = select(
        model=RoutingModel.SKILL_MATCHED,
        candidates=[_cand(available=False, skills=["hvac"])],
        now=MID,
        required_skill="hvac",
    )
    assert sel.assigned_id is None
    assert sel.accountable_id is None
    assert sel.broadcast_pool == []
    assert sel.flag is True
    assert sel.flag_reason is not None


def test_no_candidate_at_all_flags():
    sel = select(
        model=RoutingModel.SKILL_MATCHED,
        candidates=[],
        now=MID,
        required_skill="hvac",
    )
    assert sel.flag is True
    assert sel.flag_reason is not None
    assert sel.assigned_id is None


# ----------------------------------------------- stall / reassign ----------

def test_stall_reassign_excludes_stalled_assignee_picks_other():
    """Stall/reassign re-runs the SAME pure select with the stalled assignee
    excluded — the rule lives once (Spec §7.1)."""
    stalled = _cand(available=True, skills=["hvac"], active_load=0)
    backup = _cand(available=True, skills=["hvac"], active_load=3)
    # First pass: least-loaded wins -> the stalled one.
    first = select(
        model=RoutingModel.SKILL_MATCHED,
        candidates=[stalled, backup],
        now=MID,
        required_skill="hvac",
    )
    assert first.assigned_id == stalled.account_id

    # Reassign: same function, stalled assignee excluded -> backup picked.
    again = select(
        model=RoutingModel.SKILL_MATCHED,
        candidates=[stalled, backup],
        now=MID,
        required_skill="hvac",
        exclude={stalled.account_id},
    )
    assert again.assigned_id == backup.account_id
    assert again.accountable_id == backup.account_id
    assert again.flag is False


def test_stall_reassign_d12_excludes_owner_broadcasts():
    """D12 stall: owner excluded -> broadcast to remaining in-zone pool."""
    owner = _cand(available=True, is_section_owner=True, in_zone=True)
    pool = _cand(available=True, in_zone=True)
    sel = select(
        model=RoutingModel.SECTION_POOLED,
        candidates=[owner, pool],
        now=MID,
        section_id=uuid.uuid4(),
        exclude={owner.account_id},
    )
    assert sel.assigned_id is None
    assert sel.accountable_id == owner.account_id  # owner stays accountable
    assert sel.broadcast_pool == [pool.account_id]
