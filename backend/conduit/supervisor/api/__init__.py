from fastapi import APIRouter

from conduit.supervisor.api.accounts import router as accounts_router
from conduit.supervisor.api.binding import router as binding_router
from conduit.supervisor.api.decisions import router as decisions_router
from conduit.supervisor.api.setup import router as setup_router

router = APIRouter(prefix="/supervisor")
router.include_router(decisions_router)
router.include_router(setup_router)
router.include_router(accounts_router)
router.include_router(binding_router)
