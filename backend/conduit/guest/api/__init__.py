from fastapi import APIRouter

from conduit.guest.api.conversation import router as conversation_router
from conduit.guest.api.requests import router as requests_router

router = APIRouter(prefix="/guest")
# Spec §8 is authoritative: GET /guest/requests serves the dispatch status
# cards. The dispatch router is composed FIRST so its GET /requests wins the
# (otherwise-shadowed) path match; the conversation router still owns the
# distinct POST /requests (merged intake) + POST /children/* surface, so all
# existing behaviour is preserved (no merged route is removed).
router.include_router(requests_router)
router.include_router(conversation_router)
