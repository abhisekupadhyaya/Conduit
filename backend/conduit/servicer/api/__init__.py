from fastapi import APIRouter

from conduit.servicer.api.queue import router as queue_router

router = APIRouter(prefix="/servicer")
router.include_router(queue_router)
