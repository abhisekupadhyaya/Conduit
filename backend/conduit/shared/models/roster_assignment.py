# conduit/shared/models/roster_assignment.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, String, func, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class RosterAssignment(Base):
    __tablename__ = "roster_assignment"
    __table_args__ = (
        CheckConstraint(
            "assignment in ('owner','backup','member')",
            name="ck_assignment_role",
        ),
        CheckConstraint(
            "status in ('active','disabled')", name="ck_assignment_status",
        ),
        CheckConstraint(
            "assignment not in ('owner','backup') OR section_id IS NOT NULL",
            name="ck_assignment_owner_needs_section",
        ),
        Index(
            "uq_active_owner_per_section",
            "roster_id", "section_id",
            unique=True,
            postgresql_where=text("assignment = 'owner' AND status = 'active'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    roster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster.id"), nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section.id"), nullable=True,
    )
    assignment: Mapped[str] = mapped_column(String, nullable=False)
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
