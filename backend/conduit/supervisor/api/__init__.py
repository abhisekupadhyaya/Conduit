from fastapi import APIRouter

from conduit.supervisor.api.accounts import router as accounts_router
from conduit.supervisor.api.awareness import router as awareness_router
from conduit.supervisor.api.binding import router as binding_router
from conduit.supervisor.api.decisions import router as decisions_router
from conduit.supervisor.api.issue_codes import router as issue_codes_router
from conduit.supervisor.api.kb import router as kb_router
from conduit.supervisor.api.override import router as override_router
from conduit.supervisor.api.rosters import router as rosters_router
from conduit.supervisor.api.setup import router as setup_router
from conduit.supervisor.api.setup import setup_router as sla_ladder_router
from conduit.supervisor.api.staff import router as staff_router

router = APIRouter(prefix="/supervisor")
# Additive compose (Resolution E / Spec §4): the E3 decisions router owns
# the NEW ``/supervisor/decisions*`` surface (Spec §8 "Supervisor
# decisions" / §7.4); the E4 override router owns the disjoint NEW
# ``/supervisor/children*`` surface (Spec §8 "Supervisor children/override"
# — D6 god-mode). The merged staffing/no-dispatch supervisor CONFIG
# routers keep their distinct paths untouched — ``setup``/``accounts``/
# ``binding``/``issue_codes``/``staff``/``rosters``/``kb`` each own a
# disjoint path prefix. No path is shared (``children`` ≠ ``decisions`` ≠
# any CONFIG prefix), so NOTHING is shadowed and all existing supervisor
# behaviour is preserved.
router.include_router(decisions_router)
router.include_router(override_router)
router.include_router(setup_router)
# E5 (Spec §8 "Supervisor SLA/ladder CONFIG"): the SLA-preset /
# escalation-ladder CONFIG CRUD owns the disjoint NEW prefixes
# ``/supervisor/sla-presets`` + ``/supervisor/escalation-ladder`` — neither
# overlaps ``setup``/``children``/``decisions`` nor any other CONFIG path,
# so nothing is shadowed (additive, Resolution E / Spec §4).
router.include_router(sla_ladder_router)
# E6 (Spec §8/§9 "Supervisor awareness"): the awareness stream — the FIRST
# event read model — owns the disjoint NEW prefix ``/supervisor/awareness``.
# It is a WATCH-ONLY surface, deliberately DISTINCT from the E3
# ``/supervisor/decisions`` act-only queue (D2 — watch vs act, two
# separate routes; awareness is NOT folded into decisions). The prefix
# overlaps NEITHER ``decisions``/``children``/``setup``/``sla-presets``/
# ``escalation-ladder`` NOR any other CONFIG path, so nothing is shadowed
# (additive, Resolution E / Spec §4). It is also OUT of the staffing
# route-snapshot ``_STAFFING_PREFIXES`` (``/supervisor/staff`` /
# ``/supervisor/rosters`` / ``/servicer/``), so the snapshot is untouched.
router.include_router(awareness_router)
router.include_router(accounts_router)
router.include_router(binding_router)
router.include_router(issue_codes_router)
router.include_router(staff_router)
router.include_router(rosters_router)
router.include_router(kb_router)
