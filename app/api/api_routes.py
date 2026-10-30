from fastapi import APIRouter

from app.api.system.controllers.system_controller import (
    diagnostics_router,
    metrics_router,
)
from app.api.system.controllers.system_controller import router as system_router
from app.api.v1.v1_routes import router as v1_router


def create_router(*, diagnostics_enabled: bool, metrics_enabled: bool) -> APIRouter:
    # Build per application so differently configured instances cannot share exposure.
    router = APIRouter()

    router.include_router(system_router)
    if diagnostics_enabled:
        router.include_router(diagnostics_router)

    if metrics_enabled:
        router.include_router(metrics_router)

    api_router = APIRouter(prefix="/api")

    api_router.include_router(v1_router)
    router.include_router(api_router)

    return router
