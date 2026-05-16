# conduit/shared/models/provenance.py
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class NDProvenanceKB(Base):
    __tablename__ = "nd_provenance_kb"
    resolution_child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("no_dispatch_resolution.child_id"),
        primary_key=True)
    kb_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_entry.id"), primary_key=True)
    claimed_used: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                               server_default="false")


class NDProvenanceField(Base):
    __tablename__ = "nd_provenance_field"
    __table_args__ = (
        CheckConstraint(
            "field_name in ('room_label','section_label','check_in',"
            "'check_out','stay_status')", name="ck_ndpf_field"),
    )
    resolution_child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("no_dispatch_resolution.child_id"),
        primary_key=True)
    field_name: Mapped[str] = mapped_column(String, primary_key=True)
    claimed_used: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                               server_default="false")
