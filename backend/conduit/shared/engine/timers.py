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

from enum import Enum


class TimerType(str, Enum):
    ACCEPT_WINDOW = "accept_window"
    FULFILMENT_SLA = "fulfilment_sla"
    SUPERVISOR_SLA = "supervisor_sla"
    BACKSTOP_CYCLE = "backstop_cycle"


def arm(subject_type: str, subject_id: str, timer_type: TimerType) -> None:
    raise NotImplementedError


def cancel_for(subject_type: str, subject_id: str) -> None:
    """Cancel pending timers (cancel/modify, D37/D38)."""
    raise NotImplementedError
