from fastapi import APIRouter

from app.controllers.item_controller import router as items_router

router = APIRouter(prefix="/v1")

router.include_router(items_router, prefix="/items", tags=["Items"])
