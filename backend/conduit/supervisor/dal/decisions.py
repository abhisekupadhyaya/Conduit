# conduit/supervisor/dal/decisions.py
"""Supervisor decision-queue reads (Spec §8 / §7.4 / §9.2). Read-only:
add-only / no-flush / no-commit (the merged DAL discipline).

Resolution E (spec §4 "Portal ownership"): the supervisor owns its own
decision-queue reads through THIS module; it must NOT import another
portal's DAL. The read joins, for each escalation:

* the ``Escalation`` row itself (state / trigger / ``cycle_count``);
* its ``Recommendation`` + the thin per-action ``rec_*`` detail row
  (the C2-built draft the supervisor approves/edits/overrides — D7: the
  human never gets a blank ticket);
* the pending ``supervisor_sla`` ``Timer``'s ``fire_at`` — the live
  countdown DEADLINE (D9). A ``hard_escalated`` (duty-manager) item is
  NON-time-boxed (D21) and has no live supervisor-SLA timer.

The ``?status`` filter selects which escalation states to surface
(default: ``open`` — the actionable decision queue). Self-scoped: a
supervisor sees the property-wide decision queue (decisions are not
per-user), but the read NEVER widens past the escalation rows and never
flushes/commits.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import (Escalation, Recommendation, RecExtendSla,
                                   RecReassign, RecRelocate, Timer)

# A decision is "live" / actionable while it is ``open`` — the default
# queue. Resolved/terminal states are reachable only via an explicit
# ``?status`` filter (audit / ledger view).
_DEFAULT_STATUS = "open"

# D21: the non-time-boxed duty-manager backstop.
_HARD_ESCALATED = "hard_escalated"


async def _rec_detail(s: AsyncSession, escalation_id: uuid.UUID,
                      action: str) -> dict:
    """The thin per-action ``rec_*`` detail row as a curated dict, keyed by
    the exact ``ck_rec_action`` vocabulary. broadcast/approve/deny carry no
    params (empty detail)."""
    if action == "reassign":
        d = (await s.execute(select(RecReassign).where(
            RecReassign.recommendation_escalation_id == escalation_id)
        )).scalar_one_or_none()
        return {"target_account_id": str(d.target_account_id)} if d else {}
    if action == "relocate":
        d = (await s.execute(select(RecRelocate).where(
            RecRelocate.recommendation_escalation_id == escalation_id)
        )).scalar_one_or_none()
        return {"target_room_id": str(d.target_room_id)} if d else {}
    if action == "extend_sla":
        d = (await s.execute(select(RecExtendSla).where(
            RecExtendSla.recommendation_escalation_id == escalation_id)
        )).scalar_one_or_none()
        return {"extend_seconds": d.extend_seconds} if d else {}
    return {}  # broadcast / approve / deny — no params


async def list_decisions(s: AsyncSession,
                         status: str | None = None) -> list[dict]:
    """The decision queue: escalations at ``status`` (default ``open``) with
    their AI recommendation + per-action detail + the supervisor-SLA
    countdown deadline + ``cycle_count``. Read-only — no flush, no commit.

    ``non_time_boxed`` is True for a ``hard_escalated`` item (D21 — the
    duty-manager backstop is not time-boxed); its
    ``supervisor_sla_deadline`` is whatever pending supervisor_sla timer
    remains (typically None — the silence path is disabled past the bound).
    """
    want = status or _DEFAULT_STATUS
    escs = (await s.execute(
        select(Escalation).where(Escalation.state == want)
        .order_by(Escalation.created_at)
    )).scalars().all()

    out: list[dict] = []
    for esc in escs:
        rec = (await s.execute(select(Recommendation).where(
            Recommendation.escalation_id == esc.id))).scalar_one_or_none()
        rec_out = None
        if rec is not None:
            rec_out = {
                "action": rec.action,
                "rationale_text": rec.rationale_text,
                "detail": await _rec_detail(s, esc.id, rec.action),
            }
        # The live supervisor-SLA countdown DEADLINE (D9): the pending
        # supervisor_sla Timer's fire_at. A hard-escalated item is NOT
        # time-boxed (D21).
        deadline = (await s.execute(
            select(Timer.fire_at).where(
                Timer.escalation_id == esc.id,
                Timer.type == "supervisor_sla",
                Timer.state == "pending",
            ).order_by(Timer.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        out.append({
            "escalation_id": str(esc.id),
            "child_id": str(esc.child_id),
            "trigger": esc.trigger,
            "state": esc.state,
            "cycle_count": esc.cycle_count,
            "supervisor_sla_deadline": deadline,
            "non_time_boxed": esc.state == _HARD_ESCALATED,
            "recommendation": rec_out,
        })
    return out


async def get_open_escalation(
    s: AsyncSession, escalation_id: uuid.UUID
) -> Escalation | None:
    """The Escalation ONLY if it is still ``open`` (resolvable). A
    non-existent OR already-resolved escalation is INDISTINGUISHABLE here →
    the service maps both to ``ConflictError`` (409 — no resolve possible /
    already resolved; no enumeration oracle)."""
    return (await s.execute(
        select(Escalation).where(
            Escalation.id == escalation_id,
            Escalation.state == "open",
        )
    )).scalar_one_or_none()
