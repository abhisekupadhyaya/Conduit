from fastapi import APIRouter

from conduit.servicer.api.queue import router as queue_router
from conduit.servicer.api.self import router as self_router

router = APIRouter(prefix="/servicer")
router.include_router(queue_router)
router.include_router(self_router)
