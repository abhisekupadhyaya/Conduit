# conduit/shared/models/escalation.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class Escalation(Base):
    __tablename__ = "escalation"
    __table_args__ = (
        CheckConstraint(
            "trigger in ('triage_flag','stall','servicer_raised')",
            name="ck_esc_trigger",
        ),
        CheckConstraint(
            "state in ('open','approved','edited','overridden',"
            "'auto_proceeded','hard_escalated')",
            name="ck_esc_state",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(
        String, nullable=False, server_default="open",
    )
    cycle_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    raised_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=True,
    )
    resolved_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=True,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
