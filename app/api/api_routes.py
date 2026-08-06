from fastapi import APIRouter

from app.api.system.controllers.system_controller import router as system_router
from app.api.v1.v1_routes import router as v1_router

api_router: APIRouter = APIRouter(prefix="/api")
api_router.include_router(v1_router)

router: APIRouter = APIRouter()
router.include_router(system_router)
router.include_router(api_router)
