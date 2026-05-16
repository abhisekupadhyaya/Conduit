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
            "'child_deferred','child_parked','child_closed','child_reopened')",
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
