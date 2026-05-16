"""Public slice — login + health. No auth required to reach these."""
from fastapi import APIRouter

from conduit.public.api.auth import router as auth_router
from conduit.public.api.health import router as health_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
