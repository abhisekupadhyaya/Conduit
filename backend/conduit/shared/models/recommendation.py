# conduit/shared/models/recommendation.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class Recommendation(Base):
    __tablename__ = "recommendation"
    __table_args__ = (
        CheckConstraint(
            "action in ('reassign','broadcast','relocate',"
            "'extend_sla','approve','deny')",
            name="ck_rec_action",
        ),
    )
    escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation.id"), primary_key=True,
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    rationale_text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class _RecDetail(Base):
    __abstract__ = True
    recommendation_escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendation.escalation_id"),
        primary_key=True,
    )


class RecReassign(_RecDetail):
    __tablename__ = "rec_reassign"
    target_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )


class RecRelocate(_RecDetail):
    __tablename__ = "rec_relocate"
    target_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False,
    )


class RecExtendSla(_RecDetail):
    __tablename__ = "rec_extend_sla"
    extend_seconds: Mapped[int] = mapped_column(Integer, nullable=False)


class RecApprove(_RecDetail):
    __tablename__ = "rec_approve"


class RecDeny(_RecDetail):
    __tablename__ = "rec_deny"


class RecBroadcast(_RecDetail):
    __tablename__ = "rec_broadcast"
