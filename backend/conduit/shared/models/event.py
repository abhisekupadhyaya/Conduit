# conduit/shared/models/event.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class Event(Base):
    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint(
            "type in ('stay_created','stay_ended','guest_relocated',"
            "'request_created','child_triaged','child_answered',"
            "'child_deferred','child_parked','child_closed','child_reopened',"
            "'staff_profile_created','staff_profile_updated',"
            "'staff_skills_set','roster_created','roster_updated',"
            "'assignment_created','assignment_updated','presence_changed',"
            "'work_order_created','work_order_pushed','work_order_broadcast',"
            "'work_order_accepted','work_order_in_progress',"
            "'work_order_completed','work_order_cancelled','child_routed',"
            "'child_done_pending_confirm','child_closed_confirmed',"
            "'child_reopened_by_guest','child_cancelled','escalation_opened',"
            "'escalation_resolved','recommendation_created','glitch_opened',"
            "'glitch_closed','cross_dept_notified','timer_fired',"
            "'sla_preset_created','sla_preset_updated',"
            "'escalation_ladder_created','escalation_ladder_updated',"
            "'reservation_mutated')",
            name="ck_event_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String, nullable=False)
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=True)
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class EventStayCreated(Base):
    __tablename__ = "event_stay_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)


class EventStayEnded(Base):
    __tablename__ = "event_stay_ended"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)


class EventGuestRelocated(Base):
    __tablename__ = "event_guest_relocated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)
    from_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False)
    to_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False)


class EventRequestCreated(Base):
    __tablename__ = "event_request_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request.id"), nullable=False)


class _ChildEvent(Base):
    __abstract__ = True
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=False)


class EventChildTriaged(_ChildEvent):
    __tablename__ = "event_child_triaged"


class EventChildDeferred(_ChildEvent):
    __tablename__ = "event_child_deferred"


class EventChildParked(_ChildEvent):
    __tablename__ = "event_child_parked"


class EventChildClosed(_ChildEvent):
    __tablename__ = "event_child_closed"


class EventChildReopened(_ChildEvent):
    __tablename__ = "event_child_reopened"


class EventChildAnswered(Base):
    __tablename__ = "event_child_answered"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=False)
    resolution_child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("no_dispatch_resolution.child_id"),
        nullable=False)


class EventStaffProfileCreated(Base):
    __tablename__ = "event_staff_profile_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )


class EventStaffProfileUpdated(Base):
    __tablename__ = "event_staff_profile_updated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )


class EventStaffSkillsSet(Base):
    __tablename__ = "event_staff_skills_set"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )


class EventRosterCreated(Base):
    __tablename__ = "event_roster_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    roster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster.id"), nullable=False,
    )


class EventRosterUpdated(Base):
    __tablename__ = "event_roster_updated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    roster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster.id"), nullable=False,
    )


class EventAssignmentCreated(Base):
    __tablename__ = "event_assignment_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_assignment.id"), nullable=False,
    )


class EventAssignmentUpdated(Base):
    __tablename__ = "event_assignment_updated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_assignment.id"), nullable=False,
    )


class EventPresenceChanged(Base):
    __tablename__ = "event_presence_changed"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )


class EventWorkOrderCreated(Base):
    __tablename__ = "event_work_order_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False,
    )


class EventWorkOrderPushed(Base):
    __tablename__ = "event_work_order_pushed"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False,
    )


class EventWorkOrderBroadcast(Base):
    __tablename__ = "event_work_order_broadcast"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False,
    )


class EventWorkOrderAccepted(Base):
    __tablename__ = "event_work_order_accepted"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False,
    )


class EventWorkOrderInProgress(Base):
    __tablename__ = "event_work_order_in_progress"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False,
    )


class EventWorkOrderCompleted(Base):
    __tablename__ = "event_work_order_completed"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False,
    )


class EventWorkOrderCancelled(Base):
    __tablename__ = "event_work_order_cancelled"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False,
    )


class EventChildRouted(_ChildEvent):
    __tablename__ = "event_child_routed"


class EventChildDonePendingConfirm(_ChildEvent):
    __tablename__ = "event_child_done_pending_confirm"


class EventChildClosedConfirmed(_ChildEvent):
    __tablename__ = "event_child_closed_confirmed"


class EventChildReopenedByGuest(_ChildEvent):
    __tablename__ = "event_child_reopened_by_guest"


class EventChildCancelled(_ChildEvent):
    __tablename__ = "event_child_cancelled"


class EventEscalationOpened(Base):
    __tablename__ = "event_escalation_opened"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation.id"), nullable=False,
    )


class EventEscalationResolved(Base):
    __tablename__ = "event_escalation_resolved"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation.id"), nullable=False,
    )


class EventRecommendationCreated(Base):
    __tablename__ = "event_recommendation_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    recommendation_escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendation.escalation_id"),
        nullable=False,
    )


class EventGlitchOpened(Base):
    __tablename__ = "event_glitch_opened"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    glitch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("glitch.id"), nullable=False,
    )


class EventGlitchClosed(Base):
    __tablename__ = "event_glitch_closed"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    glitch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("glitch.id"), nullable=False,
    )


class EventCrossDeptNotified(Base):
    __tablename__ = "event_cross_dept_notified"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    cross_dept_notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cross_dept_notification.id"),
        nullable=False,
    )


class EventTimerFired(Base):
    __tablename__ = "event_timer_fired"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    timer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("timer.id"), nullable=False,
    )


class EventSlaPresetCreated(Base):
    __tablename__ = "event_sla_preset_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    sla_preset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sla_preset.id"), nullable=False,
    )


class EventSlaPresetUpdated(Base):
    __tablename__ = "event_sla_preset_updated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    sla_preset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sla_preset.id"), nullable=False,
    )


class EventEscalationLadderCreated(Base):
    __tablename__ = "event_escalation_ladder_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    escalation_ladder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation_ladder.id"), nullable=False,
    )


class EventEscalationLadderUpdated(Base):
    __tablename__ = "event_escalation_ladder_updated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    escalation_ladder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation_ladder.id"), nullable=False,
    )


class EventReservationMutated(Base):
    __tablename__ = "event_reservation_mutated"
    __table_args__ = (
        CheckConstraint("field = 'check_out'",
                        name="ck_event_resv_mut_field"),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    new_value: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
