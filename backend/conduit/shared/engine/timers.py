"""Durable timers (AD5/D23/D9/D21).

Timer rows are written in the SAME transaction as the state transition that
creates them. Time source is the DB's now(), never the host clock.

Types:
  accept_window   — D23: did anyone take ownership?
  fulfilment_sla  — D23/D15: was it done in time?
  supervisor_sla  — D9: the time-boxed checkpoint
  backstop_cycle  — D21: bounded auto-cycles → hard-escalate duty manager
Stall fires on whichever of the first two breaches first.
"""
from __future__ import annotations

import datetime as dt
import uuid
from enum import Enum

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import Timer


class TimerType(str, Enum):
    ACCEPT_WINDOW = "accept_window"
    FULFILMENT_SLA = "fulfilment_sla"
    SUPERVISOR_SLA = "supervisor_sla"
    BACKSTOP_CYCLE = "backstop_cycle"


_SUBJECT = {"child_id": "child_id", "work_order_id": "work_order_id",
            "escalation_id": "escalation_id"}


async def arm(s: AsyncSession, subject_kind: str, subject_id: uuid.UUID,
              timer_type: TimerType, *, fire_at: dt.datetime,
              cycle: int | None = None) -> Timer:
    col = _SUBJECT[subject_kind]
    t = Timer(type=timer_type.value, fire_at=fire_at, cycle=cycle,
              **{col: subject_id})
    s.add(t)
    return t


async def cancel_for(s: AsyncSession, subject_kind: str,
                     subject_id: uuid.UUID) -> None:
    """Cancel pending timers (cancel/modify, D37/D38)."""
    col = _SUBJECT[subject_kind]
    await s.execute(update(Timer)
        .where(getattr(Timer, col) == subject_id, Timer.state == "pending")
        .values(state="cancelled"))
