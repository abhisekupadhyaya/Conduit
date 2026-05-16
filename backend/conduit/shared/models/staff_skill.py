# conduit/shared/models/staff_skill.py
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class StaffSkill(Base):
    __tablename__ = "staff_skill"
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), primary_key=True,
    )
    skill: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
