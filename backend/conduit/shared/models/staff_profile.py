# conduit/shared/models/staff_profile.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class StaffProfile(Base):
    __tablename__ = "staff_profile"
    __table_args__ = (
        CheckConstraint(
            "staff_class in "
            "('housekeeping','engineering','room_service','concierge','runner')",
            name="ck_staff_profile_class",
        ),
        CheckConstraint(
            "presence in ('working','on_break','off')",
            name="ck_staff_profile_presence",
        ),
        CheckConstraint(
            "status in ('active','disabled')",
            name="ck_staff_profile_status",
        ),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), primary_key=True,
    )
    staff_class: Mapped[str] = mapped_column(String, nullable=False)
    presence: Mapped[str] = mapped_column(
        String, nullable=False, server_default="working",
    )
    presence_set_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
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
