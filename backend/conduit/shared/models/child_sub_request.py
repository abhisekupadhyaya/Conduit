# conduit/shared/models/child_sub_request.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class ChildSubRequest(Base):
    __tablename__ = "child_sub_request"
    __table_args__ = (
        CheckConstraint("outcome in ('auto','clarify','flag','no_dispatch')",
                        name="ck_child_outcome"),
        CheckConstraint(
            "fulfilment_mode is null or fulfilment_mode in ('dispatch','no_dispatch')",
            name="ck_child_mode"),
        CheckConstraint(
            "state in ('intake','triaged','answered','concierge_queue',"
            "'closed','reopened')", name="ck_child_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request.id"), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    issue_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issue_code.id"), nullable=True)
    uncategorized: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                server_default="false")
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    fulfilment_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    is_problem_report: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                    server_default="false")
    state: Mapped[str] = mapped_column(String, nullable=False,
                                       server_default="intake")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
