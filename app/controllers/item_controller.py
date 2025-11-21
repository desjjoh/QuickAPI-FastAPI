from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.database.entities.item_orm import ItemORM
from app.models.item_model import ItemIn, ItemOut

router = APIRouter()


@router.post("/", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: ItemIn, db: AsyncSession = Depends(get_session)
) -> ItemOut:
    try:
        item = ItemORM(name=payload.name, price=payload.price)
        db.add(item)
        await db.commit()
        await db.refresh(item)

        created = ItemOut.model_validate(item)
        return created

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create item")


@router.get("/", response_model=list[ItemOut])
async def list_items(db: AsyncSession = Depends(get_session)) -> list[ItemOut]:
    try:
        res = await db.execute(select(ItemORM).order_by(ItemORM.id))
        items = res.scalars().all()
        return [ItemOut.model_validate(i) for i in items]

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to retrieve items")


@router.get("/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, db: AsyncSession = Depends(get_session)) -> ItemOut:
    res = await db.execute(select(ItemORM).where(ItemORM.id == item_id))
    obj = res.scalar_one_or_none()

    if not obj:
        raise HTTPException(status_code=404, detail="Item not found")

    found = ItemOut.model_validate(obj)
    return found


@router.patch("/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: int, payload: ItemIn, db: AsyncSession = Depends(get_session)
) -> ItemOut:
    res = await db.execute(select(ItemORM).where(ItemORM.id == item_id))
    obj = res.scalar_one_or_none()

    if not obj:
        raise HTTPException(status_code=404, detail="Item not found")

    obj.name = payload.name
    obj.price = payload.price
    await db.commit()
    await db.refresh(obj)

    updated = ItemOut.model_validate(obj)
    return updated


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, db: AsyncSession = Depends(get_session)) -> None:
    res = await db.execute(select(ItemORM).where(ItemORM.id == item_id))
    obj = res.scalar_one_or_none()

    if not obj:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.delete(obj)
    await db.commit()
