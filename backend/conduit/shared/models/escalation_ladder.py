# conduit/shared/models/escalation_ladder.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class EscalationLadder(Base):
    __tablename__ = "escalation_ladder"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','disabled')",
            name="ck_ladder_status",
        ),
        CheckConstraint(
            "n_cycle_bound > 0",
            name="ck_ladder_nbound",
        ),
        Index(
            "uq_ladder_active_property", "property_id",
            unique=True, postgresql_where="status = 'active'",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id"), nullable=False,
    )
    duty_manager_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )
    n_cycle_bound: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="active",
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
