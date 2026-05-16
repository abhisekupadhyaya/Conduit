# conduit/shared/models/glitch.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class Glitch(Base):
    __tablename__ = "glitch"
    __table_args__ = (
        CheckConstraint(
            "state in ('open','held_open','auto_closed','closed')",
            name="ck_glitch_state",
        ),
        CheckConstraint(
            "opened_from in ('problem_report','dispute')",
            name="ck_glitch_origin",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"),
        nullable=False, unique=True,
    )
    state: Mapped[str] = mapped_column(
        String, nullable=False, server_default="open",
    )
    opened_from: Mapped[str] = mapped_column(String, nullable=False)
    recovery_owed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    recovery_cost: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
