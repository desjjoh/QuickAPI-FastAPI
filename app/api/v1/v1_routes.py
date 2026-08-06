from fastapi import APIRouter

from app.api.v1.items.controllers.item_controller import router as items_router

router: APIRouter = APIRouter(prefix="/v1")

router.include_router(items_router, prefix="/items", tags=["Items"])
