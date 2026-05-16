# conduit/supervisor/services/issue_codes.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError, NotFoundError, ValidationError
from conduit.supervisor.dal import issue_codes as dal

_MODE = {"dispatch", "no_dispatch"}
_ROUTING = {"section_pooled", "skill_matched", "none"}
_INTENT = {"service", "problem_report"}


def _validate(mode=None, routing=None, intent=None):
    if mode is not None and mode not in _MODE:
        raise ValidationError("invalid fulfilment_mode")
    if routing is not None and routing not in _ROUTING:
        raise ValidationError("invalid routing_model")
    if intent is not None and intent not in _INTENT:
        raise ValidationError("invalid intent_kind")


async def list_codes(s, status=None):
    return await dal.list_codes(s, status=status)


async def create_code(s: AsyncSession, *, code, label, department,
                       fulfilment_mode, routing_model, intent_kind, actor):
    _validate(fulfilment_mode, routing_model, intent_kind)
    if await dal.get_by_code(s, code) is not None:
        raise ConflictError("issue code already exists")
    obj = await dal.insert(s, code=code, label=label, department=department,
                            fulfilment_mode=fulfilment_mode,
                            routing_model=routing_model,
                            intent_kind=intent_kind)
    # is_reservation_mutation intentionally NOT settable here (Resolution A)
    await s.flush()
    return obj


async def update_code(s: AsyncSession, code_id: uuid.UUID, *, actor, **fields):
    obj = await dal.get(s, code_id)
    if obj is None:
        raise NotFoundError("issue code not found")
    _validate(fields.get("fulfilment_mode"), fields.get("routing_model"),
              fields.get("intent_kind"))
    if "status" in fields and fields["status"] not in (None, "active",
                                                        "disabled"):
        raise ValidationError("invalid status")
    new_code = fields.get("code")
    if new_code and new_code.lower() != obj.code.lower():
        if await dal.get_by_code(s, new_code) is not None:
            raise ConflictError("issue code already exists")
    await dal.update(s, obj, **fields)
    await s.flush()
    return obj
