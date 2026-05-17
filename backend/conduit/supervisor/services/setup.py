# conduit/supervisor/services/setup.py
"""Supervisor SLA/ladder CONFIG (Spec §8; D15 SLA presets, D21 escalation
ladder + duty manager).

Mirrors the merged ``issue_codes`` CONFIG service idiom VERBATIM: validate
(coherence guards raise ``ValidationError`` → 422 exactly like
``issue_codes._validate``), a duplicate ACTIVE row raises ``ConflictError``
→ 409 BEFORE the partial-unique index can leak a raw IntegrityError 500
(the index ``uq_sla_active_tier`` / ``uq_ladder_active_property`` is the
backstop, not the primary guard), insert/update via the add-only DAL, then
emit EXACTLY ONE append-only event through the existing C4 writer
``emit_*`` (no parallel event path) and ``flush``. The DAL never flushes /
commits; this service flushes; the API commits at the edge; reads never
commit. ``status='disabled'`` via PATCH is the ONLY removal — there is no
delete path (disable-not-delete).

D31 "trusts well-formed config": only the spec-stated / CHECK-backed rules
are enforced (tier in P1-P4, every duration > 0, n_cycle_bound > 0) — no
over-validation.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError, NotFoundError, ValidationError
from conduit.shared.events.writer import (
    emit_escalation_ladder_created,
    emit_escalation_ladder_updated,
    emit_sla_preset_created,
    emit_sla_preset_updated,
)
from conduit.supervisor.dal import escalation_ladder as ldal
from conduit.supervisor.dal import sla_presets as sdal

_TIER = {"P1", "P2", "P3", "P4"}
_STATUS = (None, "active", "disabled")
_SLA_SECONDS = (
    "accept_window_seconds",
    "fulfilment_sla_seconds",
    "supervisor_sla_seconds",
)


# --- SLA presets ----------------------------------------------------------
def _validate_sla(*, tier=None, status=None, **seconds):
    if tier is not None and tier not in _TIER:
        raise ValidationError("invalid tier")
    if status not in _STATUS:
        raise ValidationError("invalid status")
    for k in _SLA_SECONDS:
        v = seconds.get(k)
        if v is not None and v <= 0:
            raise ValidationError(f"{k} must be > 0")


async def list_presets(s, status=None):
    return await sdal.list_presets(s, status=status)


async def create_preset(s: AsyncSession, *, property_id, tier,
                         accept_window_seconds, fulfilment_sla_seconds,
                         supervisor_sla_seconds, actor):
    _validate_sla(tier=tier,
                  accept_window_seconds=accept_window_seconds,
                  fulfilment_sla_seconds=fulfilment_sla_seconds,
                  supervisor_sla_seconds=supervisor_sla_seconds)
    if await sdal.get_active(s, property_id, tier) is not None:
        raise ConflictError("active SLA preset already exists for this "
                            "property/tier")
    obj = await sdal.insert(s, property_id=property_id, tier=tier,
                            accept_window_seconds=accept_window_seconds,
                            fulfilment_sla_seconds=fulfilment_sla_seconds,
                            supervisor_sla_seconds=supervisor_sla_seconds)
    await s.flush()
    await emit_sla_preset_created(s, obj.id, actor.id)
    await s.flush()
    return obj


async def update_preset(s: AsyncSession, preset_id: uuid.UUID, *, actor,
                          **fields):
    obj = await sdal.get(s, preset_id)
    if obj is None:
        raise NotFoundError("SLA preset not found")
    _validate_sla(tier=fields.get("tier"), status=fields.get("status"),
                  accept_window_seconds=fields.get("accept_window_seconds"),
                  fulfilment_sla_seconds=fields.get("fulfilment_sla_seconds"),
                  supervisor_sla_seconds=fields.get("supervisor_sla_seconds"))
    await sdal.update(s, obj, **fields)
    await s.flush()
    await emit_sla_preset_updated(s, obj.id, actor.id)
    await s.flush()
    return obj


# --- Escalation ladder ----------------------------------------------------
def _validate_ladder(*, n_cycle_bound=None, status=None):
    if status not in _STATUS:
        raise ValidationError("invalid status")
    if n_cycle_bound is not None and n_cycle_bound <= 0:
        raise ValidationError("n_cycle_bound must be > 0")


async def list_ladders(s, status=None):
    return await ldal.list_ladders(s, status=status)


async def create_ladder(s: AsyncSession, *, property_id,
                          duty_manager_account_id, n_cycle_bound, actor):
    _validate_ladder(n_cycle_bound=n_cycle_bound)
    if await ldal.get_active(s, property_id) is not None:
        raise ConflictError("active escalation ladder already exists for "
                            "this property")
    obj = await ldal.insert(s, property_id=property_id,
                            duty_manager_account_id=duty_manager_account_id,
                            n_cycle_bound=n_cycle_bound)
    await s.flush()
    await emit_escalation_ladder_created(s, obj.id, actor.id)
    await s.flush()
    return obj


async def update_ladder(s: AsyncSession, ladder_id: uuid.UUID, *, actor,
                          **fields):
    obj = await ldal.get(s, ladder_id)
    if obj is None:
        raise NotFoundError("escalation ladder not found")
    _validate_ladder(n_cycle_bound=fields.get("n_cycle_bound"),
                      status=fields.get("status"))
    await ldal.update(s, obj, **fields)
    await s.flush()
    await emit_escalation_ladder_updated(s, obj.id, actor.id)
    await s.flush()
    return obj
