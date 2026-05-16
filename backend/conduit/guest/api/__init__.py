from fastapi import APIRouter

from conduit.guest.api.conversation import router as conversation_router

router = APIRouter(prefix="/guest")
router.include_router(conversation_router)
