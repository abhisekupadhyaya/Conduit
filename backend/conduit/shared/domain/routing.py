"""Routing — two distinct allocation models over one escalation spine.

Pure mechanism (Spec §7.1): no DB, no I/O, no clock. Inputs are
already-fetched candidate rows/dataclasses plus an explicit ``now``.
``select(...)`` returns a :class:`Selection`; effecting (create WorkOrder,
arm timers, emit events) lives in the Phase C4 lifecycle orchestrator, never
here. Stall/reassign/auto-proceed re-run this SAME ``select`` with the
stalled assignee excluded — the D12/D18 rule lives exactly once.

- Housekeeping (D12): section-pooled. Push to the positional owner; busy ⇒
  claim-fallback broadcast to the in-zone effective_available pool. The owner
  stays accountable to Closed/SLA regardless of who later claims.
- Engineering (D18): skill-scarce. Skill-match → least-loaded → priority
  queue (P1 preempts) → the matched engineer is accountable.

Only effective_available servicers are considered (D39); availability is
NEVER re-derived here — staffing's pure
``availability.effective_available(profile, assignments, now)`` is the single
source of truth and is called per candidate.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from conduit.shared.domain import availability

# P1 highest → P4 lowest (WorkOrder.priority_tier CHECK vocabulary). P1
# preempts on a load tie (Spec §7.1, D18); lower index == higher precedence.
_TIER_ORDER = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}


class RoutingModel(str, Enum):
    SECTION_POOLED = "section_pooled"  # D12
    SKILL_MATCHED = "skill_matched"  # D18


@dataclass(frozen=True)
class Candidate:
    """An already-fetched servicer row + derived load. ``profile`` and
    ``assignments`` are passed straight to the real
    ``availability.effective_available`` (its exact signature) — routing
    never inspects presence/shift itself."""

    account_id: Any
    profile: Any
    assignments: Iterable[Any]
    skills: tuple[str, ...] = ()
    active_load: int = 0
    is_section_owner: bool = False
    in_zone: bool = True
    priority_tier: str = "P3"


@dataclass(frozen=True)
class Selection:
    """The pure routing decision. No side effects implied."""

    assigned_id: Any | None = None
    accountable_id: Any | None = None
    broadcast_pool: list[Any] = field(default_factory=list)
    section_id: Any | None = None
    queue_position: int | None = None
    flag: bool = False
    flag_reason: str | None = None


def _available(c: Candidate, now: dt.datetime) -> bool:
    # Single source of truth — staffing's pure predicate, never re-derived.
    return availability.effective_available(c.profile, c.assignments, now)


def select(
    *,
    model: RoutingModel,
    candidates: Iterable[Candidate],
    now: dt.datetime,
    section_id: Any | None = None,
    required_skill: str | None = None,
    exclude: set[Any] | None = None,
) -> Selection:
    """Pure allocation per Spec §7.1. ``exclude`` is the stall/reassign hook:
    the same rule, the stalled assignee filtered out."""
    excluded = exclude or set()
    all_candidates = list(candidates)
    pool = [c for c in all_candidates if c.account_id not in excluded]

    if model is RoutingModel.SECTION_POOLED:
        return _select_section_pooled(all_candidates, pool, now, section_id)
    return _select_skill_matched(pool, now, required_skill)


def _select_section_pooled(
    all_candidates: list[Candidate],
    pool: list[Candidate],
    now: dt.datetime,
    section_id: Any | None,
) -> Selection:
    # D12: the section's positional owner is accountable regardless of who
    # later claims. Owner *identity* is found across the FULL positional set
    # (pre-exclude): stall/reassign removes the owner from *assignment*, never
    # from *accountability* — the owner stays accountable to Closed/SLA.
    owner = next(
        (c for c in all_candidates if c.is_section_owner), None
    )
    owner_id = owner.account_id if owner is not None else None
    # The owner may be assigned only if still in the (post-exclude) pool.
    owner_assignable = owner is not None and any(
        c.account_id == owner.account_id for c in pool
    )

    if owner is not None and owner_assignable and _available(owner, now):
        return Selection(
            assigned_id=owner.account_id,
            accountable_id=owner.account_id,
            section_id=section_id,
        )

    # Owner busy (or excluded by stall/reassign) ⇒ claim-fallback broadcast
    # to the in-zone effective_available pool. Owner stays accountable.
    broadcast = [
        c.account_id
        for c in pool
        if not c.is_section_owner and c.in_zone and _available(c, now)
    ]
    if broadcast:
        return Selection(
            assigned_id=None,
            accountable_id=owner_id,
            broadcast_pool=broadcast,
            section_id=section_id,
        )

    # No owner and no in-zone pool ⇒ flag (never a silent drop).
    return Selection(
        accountable_id=owner_id,
        section_id=section_id,
        flag=True,
        flag_reason="d12_no_owner_no_inzone_pool",
    )


def _select_skill_matched(
    candidates: list[Candidate], now: dt.datetime, required_skill: str | None
) -> Selection:
    # D18: effective_available engineers whose StaffSkill matches →
    # least-loaded (fewest active work orders) → tie: priority_tier ordering
    # (P1 preempts). The matched engineer is accountable.
    eligible = [
        c
        for c in candidates
        if _available(c, now)
        and (required_skill is None or required_skill in c.skills)
    ]
    if not eligible:
        return Selection(
            flag=True, flag_reason="d18_no_skill_matched_available_engineer"
        )

    # Sort key: fewest active work orders, then P1-preempts tier ordering.
    eligible.sort(
        key=lambda c: (c.active_load, _TIER_ORDER.get(c.priority_tier, 99))
    )
    chosen = eligible[0]
    return Selection(
        assigned_id=chosen.account_id,
        accountable_id=chosen.account_id,
        queue_position=0,
    )
