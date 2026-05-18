# conduit/shared/models/no_dispatch_resolution.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class NoDispatchResolution(Base):
    __tablename__ = "no_dispatch_resolution"
    __table_args__ = (
        CheckConstraint(
            "mode in ('grounded_answer','human_deferral',"
            "'reservation_mutation')", name="ck_ndr_mode"),
        CheckConstraint("helpful is null or helpful in ('yes','no')",
                        name="ck_ndr_helpful"),
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"),
        primary_key=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(String, nullable=True)
    helpful: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
