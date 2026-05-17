# conduit/shared/events/writer.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import (
    Event, EventRequestCreated, EventChildTriaged, EventChildAnswered,
    EventChildDeferred, EventChildParked, EventChildClosed, EventChildReopened,
    EventWorkOrderCreated, EventWorkOrderPushed, EventWorkOrderBroadcast,
    EventWorkOrderAccepted, EventWorkOrderInProgress, EventWorkOrderCompleted,
    EventWorkOrderCancelled, EventChildRouted, EventChildDonePendingConfirm,
    EventChildClosedConfirmed, EventChildReopenedByGuest, EventChildCancelled,
    EventEscalationOpened, EventEscalationResolved, EventRecommendationCreated,
    EventGlitchOpened, EventGlitchClosed, EventCrossDeptNotified,
    EventTimerFired, EventSlaPresetCreated, EventSlaPresetUpdated,
    EventEscalationLadderCreated, EventEscalationLadderUpdated,
)

_CHILD_DETAIL = {
    "child_triaged": EventChildTriaged,
    "child_deferred": EventChildDeferred,
    "child_parked": EventChildParked,
    "child_closed": EventChildClosed,
    "child_reopened": EventChildReopened,
}


async def emit_request_created(s: AsyncSession, request_id: uuid.UUID,
                               actor_account_id: uuid.UUID | None) -> None:
    e = Event(type="request_created", actor_account_id=actor_account_id)
    s.add(e)
    await s.flush()
    s.add(EventRequestCreated(event_id=e.id, request_id=request_id))


async def emit_child(s: AsyncSession, etype: str, child_id: uuid.UUID,
                     actor_account_id: uuid.UUID | None,
                     resolution_child_id: uuid.UUID | None = None) -> None:
    e = Event(type=etype, actor_account_id=actor_account_id)
    s.add(e)
    await s.flush()
    if etype == "child_answered":
        s.add(EventChildAnswered(event_id=e.id, child_id=child_id,
                                 resolution_child_id=resolution_child_id))
    else:
        s.add(_CHILD_DETAIL[etype](event_id=e.id, child_id=child_id))


# --- C4: one ``emit_*`` per new event type (mirrors ``emit_request_created``
# / ``emit_child``: insert the Event row, flush for its id, insert the thin
# detail row). The lifecycle orchestrator is the ONLY caller. -----------------

async def _emit_one(s: AsyncSession, etype: str, detail_cls, fk_col: str,
                    fk_id: uuid.UUID,
                    actor_account_id: uuid.UUID | None) -> None:
    e = Event(type=etype, actor_account_id=actor_account_id)
    s.add(e)
    await s.flush()
    s.add(detail_cls(event_id=e.id, **{fk_col: fk_id}))


async def emit_work_order_created(s, work_order_id, actor_account_id=None):
    await _emit_one(s, "work_order_created", EventWorkOrderCreated,
                    "work_order_id", work_order_id, actor_account_id)


async def emit_work_order_pushed(s, work_order_id, actor_account_id=None):
    await _emit_one(s, "work_order_pushed", EventWorkOrderPushed,
                    "work_order_id", work_order_id, actor_account_id)


async def emit_work_order_broadcast(s, work_order_id, actor_account_id=None):
    await _emit_one(s, "work_order_broadcast", EventWorkOrderBroadcast,
                    "work_order_id", work_order_id, actor_account_id)


async def emit_work_order_accepted(s, work_order_id, actor_account_id=None):
    await _emit_one(s, "work_order_accepted", EventWorkOrderAccepted,
                    "work_order_id", work_order_id, actor_account_id)


async def emit_work_order_in_progress(s, work_order_id, actor_account_id=None):
    await _emit_one(s, "work_order_in_progress", EventWorkOrderInProgress,
                    "work_order_id", work_order_id, actor_account_id)


async def emit_work_order_completed(s, work_order_id, actor_account_id=None):
    await _emit_one(s, "work_order_completed", EventWorkOrderCompleted,
                    "work_order_id", work_order_id, actor_account_id)


async def emit_work_order_cancelled(s, work_order_id, actor_account_id=None):
    await _emit_one(s, "work_order_cancelled", EventWorkOrderCancelled,
                    "work_order_id", work_order_id, actor_account_id)


async def emit_child_routed(s, child_id, actor_account_id=None):
    await _emit_one(s, "child_routed", EventChildRouted,
                    "child_id", child_id, actor_account_id)


async def emit_child_done_pending_confirm(s, child_id, actor_account_id=None):
    await _emit_one(s, "child_done_pending_confirm",
                    EventChildDonePendingConfirm, "child_id", child_id,
                    actor_account_id)


async def emit_child_closed_confirmed(s, child_id, actor_account_id=None):
    await _emit_one(s, "child_closed_confirmed", EventChildClosedConfirmed,
                    "child_id", child_id, actor_account_id)


async def emit_child_reopened_by_guest(s, child_id, actor_account_id=None):
    await _emit_one(s, "child_reopened_by_guest", EventChildReopenedByGuest,
                    "child_id", child_id, actor_account_id)


async def emit_child_cancelled(s, child_id, actor_account_id=None):
    await _emit_one(s, "child_cancelled", EventChildCancelled,
                    "child_id", child_id, actor_account_id)


async def emit_escalation_opened(s, escalation_id, actor_account_id=None):
    await _emit_one(s, "escalation_opened", EventEscalationOpened,
                    "escalation_id", escalation_id, actor_account_id)


async def emit_escalation_resolved(s, escalation_id, actor_account_id=None):
    await _emit_one(s, "escalation_resolved", EventEscalationResolved,
                    "escalation_id", escalation_id, actor_account_id)


async def emit_recommendation_created(s, recommendation_escalation_id,
                                      actor_account_id=None):
    await _emit_one(s, "recommendation_created", EventRecommendationCreated,
                    "recommendation_escalation_id",
                    recommendation_escalation_id, actor_account_id)


async def emit_glitch_opened(s, glitch_id, actor_account_id=None):
    await _emit_one(s, "glitch_opened", EventGlitchOpened,
                    "glitch_id", glitch_id, actor_account_id)


async def emit_glitch_closed(s, glitch_id, actor_account_id=None):
    await _emit_one(s, "glitch_closed", EventGlitchClosed,
                    "glitch_id", glitch_id, actor_account_id)


async def emit_cross_dept_notified(s, cross_dept_notification_id,
                                   actor_account_id=None):
    await _emit_one(s, "cross_dept_notified", EventCrossDeptNotified,
                    "cross_dept_notification_id", cross_dept_notification_id,
                    actor_account_id)


async def emit_timer_fired(s, timer_id, actor_account_id=None):
    await _emit_one(s, "timer_fired", EventTimerFired,
                    "timer_id", timer_id, actor_account_id)


async def emit_sla_preset_created(s, sla_preset_id, actor_account_id=None):
    await _emit_one(s, "sla_preset_created", EventSlaPresetCreated,
                    "sla_preset_id", sla_preset_id, actor_account_id)


async def emit_sla_preset_updated(s, sla_preset_id, actor_account_id=None):
    await _emit_one(s, "sla_preset_updated", EventSlaPresetUpdated,
                    "sla_preset_id", sla_preset_id, actor_account_id)


async def emit_escalation_ladder_created(s, escalation_ladder_id,
                                         actor_account_id=None):
    await _emit_one(s, "escalation_ladder_created",
                    EventEscalationLadderCreated, "escalation_ladder_id",
                    escalation_ladder_id, actor_account_id)


async def emit_escalation_ladder_updated(s, escalation_ladder_id,
                                         actor_account_id=None):
    await _emit_one(s, "escalation_ladder_updated",
                    EventEscalationLadderUpdated, "escalation_ladder_id",
                    escalation_ladder_id, actor_account_id)
