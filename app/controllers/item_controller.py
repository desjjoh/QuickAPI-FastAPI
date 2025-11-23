from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.database.repositories.item_repo import repo
from app.models.item_model import CreateItemRequest, ItemResponse

router = APIRouter()


## GET /
@router.get(
    "/",
    summary="Get a list of items",
    description="Retrieves a paginated list of items. Supports page, limit, sorting, and optional filtering.",
    response_model=list[ItemResponse],
    status_code=status.HTTP_200_OK,
)
async def get_all(db: AsyncSession = Depends(get_session)) -> list[ItemResponse]:
    items = await repo.get_all(db)

    return [ItemResponse.model_validate(item) for item in items]


## POST /
@router.post(
    "/",
    summary="Create a new item",
    description="Creates a new item using validated input. Returns the fully normalized item resource after persistence.",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    payload: CreateItemRequest, db: AsyncSession = Depends(get_session)
) -> ItemResponse:
    created = await repo.create(db, item_in=payload)

    return ItemResponse.model_validate(created)


## GET /:id
@router.get(
    "/{id}",
    summary="Get a single item by ID",
    response_model=ItemResponse,
    status_code=status.HTTP_200_OK,
)
async def get(id: str, db: AsyncSession = Depends(get_session)) -> ItemResponse:
    found = await repo.get_by_id(db, id)

    return ItemResponse.model_validate(found)


# @router.patch("/{id}", response_model=ItemOut)
# async def update(
#     id: int, payload: ItemIn, db: AsyncSession = Depends(get_session)
# ) -> ItemOut:
#     res = await db.execute(select(ItemORM).where(ItemORM.id == id))
#     obj = res.scalar_one_or_none()

#     if not obj:
#         raise HTTPException(status_code=404, detail="Item not found")

#     obj.name = payload.name
#     obj.price = payload.price
#     await db.commit()
#     await db.refresh(obj)

#     updated = ItemOut.model_validate(obj)
#     return updated


# @router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
# async def delete(id: int, db: AsyncSession = Depends(get_session)) -> None:
#     res = await db.execute(select(ItemORM).where(ItemORM.id == id))
#     obj = res.scalar_one_or_none()

#     if not obj:
#         raise HTTPException(status_code=404, detail="Item not found")

#     await db.delete(obj)
#     await db.commit()
