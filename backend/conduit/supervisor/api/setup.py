"""Setup / configuration: the structure the runtime runs on.

Sections + room→section, per-shift rosters (D12/D18), issue-code catalog
(D34), SLA presets (D15), escalation ladder + duty manager (D21), KB (D26),
guest provisioning + stays (D3a/D29/D32). Config is data, not schema — these
are row edits, never migrations.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from conduit.core.deps import Actor, require_roles

router = APIRouter(prefix="/setup", tags=["supervisor-setup"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("")
async def get_config(actor: Actor = Depends(_sup)) -> dict[str, str]:
    raise NotImplementedError
