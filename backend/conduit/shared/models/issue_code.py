# conduit/shared/models/issue_code.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class IssueCode(Base):
    __tablename__ = "issue_code"
    __table_args__ = (
        CheckConstraint("fulfilment_mode in ('dispatch','no_dispatch')",
                        name="ck_issue_code_mode"),
        CheckConstraint("routing_model in ('section_pooled','skill_matched','none')",
                        name="ck_issue_code_routing"),
        CheckConstraint("intent_kind in ('service','problem_report')",
                        name="ck_issue_code_intent"),
        CheckConstraint("status in ('active','disabled')",
                        name="ck_issue_code_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    department: Mapped[str] = mapped_column(String, nullable=False)
    fulfilment_mode: Mapped[str] = mapped_column(String, nullable=False)
    routing_model: Mapped[str] = mapped_column(String, nullable=False)
    intent_kind: Mapped[str] = mapped_column(String, nullable=False,
                                             server_default="service")
    is_reservation_mutation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String, nullable=False,
                                        server_default="active")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
