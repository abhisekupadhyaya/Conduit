from fastapi import APIRouter

router = APIRouter(tags=["public-health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
