"""0007 relocation subflow — issue_code.origin + ck_wo_kind widen + seed

Revision ID: 0007_relocation_subflow
Revises: 0006_conv_aa
Create Date: 2026-05-18

Additive on the spine: 1 nullable-free column via server_default
(issue_code.origin, +CHECK), 1 drop+recreate CHECK widening
(ck_wo_kind += 'relocation_move' — autogenerate cannot detect CHECK-text
changes, mirroring the 0003/0004/0005/0006 hand-written idiom), and an
idempotent insert-if-absent of the system-origin FO-GUEST-MOVE seed row.
No data migration; existing rows survive (origin -> 'guest'); clean
downgrade.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_relocation_subflow"
down_revision: str | None = "0006_conv_aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "issue_code",
        sa.Column("origin", sa.String(), nullable=False,
                  server_default="guest"))
    op.create_check_constraint(
        "ck_issue_code_origin", "issue_code",
        "origin in ('guest','system')")

    # --- drop + recreate the widened ck_wo_kind (text change undetectable) --
    op.drop_constraint("ck_wo_kind", "work_order", type_="check")
    op.create_check_constraint(
        "ck_wo_kind", "work_order",
        "kind in ('dispatch','human_concierge_answer','relocation_move')")

    # --- idempotent insert-if-absent of the system-origin seed row ----------
    op.execute(
        """
        INSERT INTO issue_code
            (id, code, label, department, fulfilment_mode, routing_model,
             intent_kind, is_reservation_mutation, status, origin,
             created_at, updated_at)
        SELECT gen_random_uuid(), 'FO-GUEST-MOVE', 'Guest move',
               'front_office', 'dispatch', 'section_pooled', 'service',
               false, 'active', 'system', now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM issue_code WHERE lower(code) = lower('FO-GUEST-MOVE')
        )
        """)


def downgrade() -> None:
    op.execute(
        "DELETE FROM issue_code WHERE lower(code) = lower('FO-GUEST-MOVE')")

    op.drop_constraint("ck_wo_kind", "work_order", type_="check")
    op.create_check_constraint(
        "ck_wo_kind", "work_order",
        "kind in ('dispatch','human_concierge_answer')")

    op.drop_constraint("ck_issue_code_origin", "issue_code", type_="check")
    op.drop_column("issue_code", "origin")
