# conduit/supervisor/dal/awareness.py
"""Supervisor awareness stream — the FIRST reader of the append-only
``event``+detail log (Spec §8/§9, the deferred read side finally
consumed). Read-only: add-only / no-flush / no-commit (the merged DAL
discipline).

Resolution E (spec §4 "Portal ownership"): the supervisor owns its own
awareness read through THIS module; it imports ONLY ``shared/models``
(never another portal's DAL).

The whole point of this slice is that the projection is computed FROM the
``event``+detail log — NOT from a direct ``SELECT * FROM glitch/work_order``
that bypasses the log. Each section's SET of items is driven by EMITTED
EVENTS; the core entity row (Escalation/WorkOrder/Glitch/Child) is joined
in ONLY for the display label/link the supervisor needs to read the
stream. Concretely, the four sections (Spec §8/§9 "incoming · task
delegation · servicer recent work · open glitches"):

* ``incoming``           ⟵ ``escalation_opened`` events whose escalation
  has NO ``escalation_resolved`` event (an opened-minus-resolved,
  event-log-derived "still incoming" set; the spec's "incoming" =
  freshly-opened, not-yet-resolved escalations on the stream).
* ``task_delegation``    ⟵ ``work_order_pushed`` / ``work_order_broadcast``
  / ``work_order_accepted`` events (the delegation/hand-off events).
* ``servicer_recent_work`` ⟵ ``work_order_in_progress`` /
  ``work_order_completed`` events (recent servicer activity), newest first.
* ``open_glitches``      ⟵ ``glitch_opened`` events LEFT JOIN
  ``glitch_closed`` events on ``glitch_id`` where NO ``glitch_closed``
  exists — the spec's opened-MINUS-closed: a glitch is on the stream while
  open and DISAPPEARS once auto/closed. Membership is event-log-driven;
  the ``glitch`` row supplies ONLY the display label (``opened_from`` /
  child link).

Polled (AD7). Read-only — no writes, no commit, no flush. The supervisor
scope is global by role (Spec §8); the read NEVER widens past what the
projection needs.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import (Account, ChildSubRequest, Event,
                                   EventEscalationOpened,
                                   EventEscalationResolved,
                                   EventGlitchClosed, EventGlitchOpened,
                                   EventWorkOrderAccepted,
                                   EventWorkOrderBroadcast,
                                   EventWorkOrderCompleted,
                                   EventWorkOrderInProgress,
                                   EventWorkOrderPushed, IssueCode, Glitch,
                                   WorkOrder)

# Cap each section so the polled read stays bounded (AD7 — a poll, not a
# firehose). Newest activity first.
_LIMIT = 100

_DELEGATION_DETAIL = (EventWorkOrderPushed, EventWorkOrderBroadcast,
                      EventWorkOrderAccepted)
_RECENT_DETAIL = (EventWorkOrderInProgress, EventWorkOrderCompleted)


async def _incoming(s: AsyncSession) -> list[dict]:
    """``escalation_opened`` events whose escalation has NO
    ``escalation_resolved`` event (opened-minus-resolved, event-log-derived
    — the "still incoming" set). The Escalation row is joined ONLY for the
    ``trigger``/``child_id`` display labels."""
    from conduit.shared.models import Escalation

    closed = select(EventEscalationResolved.escalation_id)
    rows = (await s.execute(
        select(Escalation.id, Escalation.child_id, Escalation.trigger,
               IssueCode.label, Event.at)
        .join(EventEscalationOpened,
              EventEscalationOpened.escalation_id == Escalation.id)
        .join(Event, Event.id == EventEscalationOpened.event_id)
        .outerjoin(ChildSubRequest,
                   ChildSubRequest.id == Escalation.child_id)
        .outerjoin(IssueCode,
                   IssueCode.id == ChildSubRequest.issue_code_id)
        .where(Escalation.id.notin_(closed))
        .order_by(Event.at.desc())
        .limit(_LIMIT)
    )).all()
    return [{"escalation_id": str(eid), "child_id": str(cid),
             "issue_label": label, "trigger": trig, "at": at}
            for eid, cid, trig, label, at in rows]


async def _work_order_section(s: AsyncSession, detail_clss) -> list[dict]:
    """Work-order rows whose ``work_order_id`` appears in ANY of the given
    event detail tables (membership is EVENT-driven). The WorkOrder row is
    joined ONLY for the ``child_id``/``servicer_id`` display labels; newest
    emitting event first."""
    out: dict = {}
    for detail_cls in detail_clss:
        rows = (await s.execute(
            select(WorkOrder.id, WorkOrder.child_id,
                   WorkOrder.assigned_servicer_id, IssueCode.label,
                   Account.display_name, Event.at)
            .join(detail_cls, detail_cls.work_order_id == WorkOrder.id)
            .join(Event, Event.id == detail_cls.event_id)
            .outerjoin(ChildSubRequest,
                       ChildSubRequest.id == WorkOrder.child_id)
            .outerjoin(IssueCode,
                       IssueCode.id == ChildSubRequest.issue_code_id)
            .outerjoin(Account,
                       Account.id == WorkOrder.assigned_servicer_id)
            .order_by(Event.at.desc())
            .limit(_LIMIT)
        )).all()
        for wid, cid, sid, label, sname, at in rows:
            prev = out.get(wid)
            # Keep the most-recent emitting event per work order.
            if prev is None or at > prev["at"]:
                out[wid] = {"work_order_id": str(wid),
                            "child_id": str(cid),
                            "issue_label": label,
                            "servicer_id": str(sid) if sid else None,
                            "servicer_name": sname,
                            "at": at}
    return sorted(out.values(), key=lambda r: r["at"], reverse=True)[:_LIMIT]


async def _open_glitches(s: AsyncSession) -> list[dict]:
    """``glitch_opened`` events whose ``glitch_id`` has NO ``glitch_closed``
    event — the spec's opened-MINUS-closed. Membership is purely
    event-log-driven (the ``Glitch`` row supplies ONLY the display label /
    child link). A glitch is on the stream while open and DISAPPEARS once a
    ``glitch_closed`` is appended."""
    closed = select(EventGlitchClosed.glitch_id)
    rows = (await s.execute(
        select(Glitch.id, Glitch.child_id, Glitch.opened_from,
               IssueCode.label, Event.at)
        .join(EventGlitchOpened, EventGlitchOpened.glitch_id == Glitch.id)
        .join(Event, Event.id == EventGlitchOpened.event_id)
        .outerjoin(ChildSubRequest,
                   ChildSubRequest.id == Glitch.child_id)
        .outerjoin(IssueCode,
                   IssueCode.id == ChildSubRequest.issue_code_id)
        .where(Glitch.id.notin_(closed))
        .order_by(Event.at.desc())
        .limit(_LIMIT)
    )).all()
    return [{"glitch_id": str(gid), "child_id": str(cid),
             "issue_label": label, "opened_from": of, "at": at}
            for gid, cid, of, label, at in rows]


async def awareness(s: AsyncSession) -> dict:
    """The ONE composite projection over the append-only ``event``+detail
    log: incoming · task delegation · servicer recent work · open glitches.
    Read-only — no flush, no commit."""
    return {
        "incoming": await _incoming(s),
        "task_delegation": await _work_order_section(s, _DELEGATION_DETAIL),
        "servicer_recent_work":
            await _work_order_section(s, _RECENT_DETAIL),
        "open_glitches": await _open_glitches(s),
    }
