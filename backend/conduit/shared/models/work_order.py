# conduit/shared/models/work_order.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class WorkOrder(Base):
    __tablename__ = "work_order"
    __table_args__ = (
        CheckConstraint(
            "kind in ('dispatch','human_concierge_answer')",
            name="ck_wo_kind",
        ),
        CheckConstraint(
            "routing_model in ('section_pooled','skill_matched')",
            name="ck_wo_model",
        ),
        CheckConstraint(
            "priority_tier in ('P1','P2','P3','P4')",
            name="ck_wo_tier",
        ),
        CheckConstraint(
            "state in ('created','pushed','broadcast','accepted',"
            "'in_progress','completed','cancelled')",
            name="ck_wo_state",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"),
        nullable=False, unique=True,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    routing_model: Mapped[str] = mapped_column(String, nullable=False)
    assigned_servicer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=True,
    )
    accountable_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=True,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section.id"), nullable=True,
    )
    priority_tier: Mapped[str] = mapped_column(String, nullable=False)
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(
        String, nullable=False, server_default="created",
    )
    completion_notes: Mapped[str | None] = mapped_column(
        String, nullable=True,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
