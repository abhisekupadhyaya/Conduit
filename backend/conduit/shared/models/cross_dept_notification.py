# conduit/shared/models/cross_dept_notification.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class CrossDeptNotification(Base):
    __tablename__ = "cross_dept_notification"
    __table_args__ = (
        CheckConstraint(
            "target_department in ('housekeeping','engineering',"
            "'room_service','concierge','front_desk','runner')",
            name="ck_xdn_dept",
        ),
        CheckConstraint(
            "state in ('open','acknowledged')",
            name="ck_xdn_state",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    source_work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False,
    )
    target_department: Mapped[str] = mapped_column(String, nullable=False)
    child_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=True,
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(
        String, nullable=False, server_default="open",
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
