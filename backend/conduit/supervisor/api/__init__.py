from fastapi import APIRouter

from conduit.supervisor.api.decisions import router as decisions_router
from conduit.supervisor.api.setup import router as setup_router

router = APIRouter(prefix="/supervisor")
router.include_router(decisions_router)
router.include_router(setup_router)
