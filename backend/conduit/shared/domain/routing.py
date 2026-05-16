"""Routing — two distinct allocation models over one escalation spine.

- Housekeeping (D12): section-pooled. Push to the positional owner; busy ⇒
  claim-fallback broadcast to in-zone staff. The owner stays accountable to
  Closed/SLA regardless of who executes.
- Engineering (D18): skill-scarce. Skill-match → least-loaded → priority
  queue (P1 preempts) → stall → spine.

Only on-shift, not-on-break servicers are considered (D39).
"""
from __future__ import annotations

from enum import Enum


class RoutingModel(str, Enum):
    SECTION_POOLED = "section_pooled"  # D12
    SKILL_MATCHED = "skill_matched"  # D18


def route(child_id: str, model: RoutingModel) -> None:
    """Create a work order and dispatch per the model. Starts the two timers
    (accept-window + fulfilment-SLA, D23)."""
    raise NotImplementedError
