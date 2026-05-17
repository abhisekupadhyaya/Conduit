from fastapi import APIRouter

from conduit.servicer.api.queue import router as queue_router
from conduit.servicer.api.self import router as self_router
from conduit.servicer.api.tasks import router as tasks_router

router = APIRouter(prefix="/servicer")
# Additive compose: the E2 task router owns the NEW ``/servicer/tasks*``
# surface (Spec §8 / §9.2). The merged staffing servicer routers keep their
# distinct paths untouched — ``queue_router`` owns ``/servicer/queue`` +
# ``/servicer/work-orders/*``; ``self_router`` owns ``/servicer/home`` +
# ``/servicer/presence``. No path is shared, so NOTHING is shadowed and all
# existing servicer behaviour is preserved.
router.include_router(queue_router)
router.include_router(self_router)
router.include_router(tasks_router)
