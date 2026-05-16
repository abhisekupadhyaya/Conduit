# conduit/shared/models/timer.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class Timer(Base):
    __tablename__ = "timer"
    __table_args__ = (
        CheckConstraint(
            "type in ('accept_window','fulfilment_sla',"
            "'supervisor_sla','backstop_cycle')",
            name="ck_timer_type",
        ),
        CheckConstraint(
            "state in ('pending','fired','cancelled')",
            name="ck_timer_state",
        ),
        CheckConstraint(
            "(child_id is not null)::int + (work_order_id is not null)::int "
            "+ (escalation_id is not null)::int = 1",
            name="ck_timer_one_subject",
        ),
        Index("ix_timer_state_fire_at", "state", "fire_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    child_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"),
        nullable=True,
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=True,
    )
    escalation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation.id"), nullable=True,
    )
    fire_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String, nullable=False, server_default="pending",
    )
    cycle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
