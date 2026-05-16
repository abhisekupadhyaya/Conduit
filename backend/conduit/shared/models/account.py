"""The account entity (IDENTITY). The only DB contract for the auth slice.

text + CHECK over PG enum keeps rule changes from migrating data
(datamodels principle: structure permissive, mechanism in code). Resolves
datamodels Q1 = unified account; account.id is the stable join target for
all later entities. Disable, never delete (D29).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base

ROLES = ("guest", "servicer", "supervisor", "duty_manager")
STATUSES = ("active", "disabled")


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (
        CheckConstraint(
            "role in ('guest','servicer','supervisor','duty_manager')",
            name="ck_account_role",
        ),
        CheckConstraint(
            "status in ('active','disabled')", name="ck_account_status"
        ),
        Index(
            "uq_account_username_lower",
            func.lower(text("username")),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="active"
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
