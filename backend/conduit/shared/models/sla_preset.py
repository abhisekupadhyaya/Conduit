# conduit/shared/models/sla_preset.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class SLAPreset(Base):
    __tablename__ = "sla_preset"
    __table_args__ = (
        CheckConstraint(
            "tier in ('P1','P2','P3','P4')",
            name="ck_sla_tier",
        ),
        CheckConstraint(
            "status in ('active','disabled')",
            name="ck_sla_status",
        ),
        Index(
            "uq_sla_active_tier", "property_id", "tier",
            unique=True, postgresql_where="status = 'active'",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id"), nullable=False,
    )
    tier: Mapped[str] = mapped_column(String, nullable=False)
    accept_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    fulfilment_sla_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    supervisor_sla_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
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
