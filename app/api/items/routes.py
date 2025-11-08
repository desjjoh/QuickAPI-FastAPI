from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.items.models.db_models import ItemORM
from app.api.items.models.schemas import ItemIn, ItemOut
from app.core.logging import log
from app.services.db import get_session


router = APIRouter(prefix="/items", tags=["Items"])


@router.post("/", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemIn, db: AsyncSession = Depends(get_session)) -> ItemOut:
    try:
        item = ItemORM(name=payload.name, price=payload.price)
        db.add(item)
        await db.commit()
        await db.refresh(item)

        created = ItemOut.model_validate(item)
        log.info("Item created", id=created.id, name=created.name, price=created.price)
        return created

    except Exception as e:
        log.error("Failed to create item", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to create item")


@router.get("/", response_model=List[ItemOut])
async def list_items(db: AsyncSession = Depends(get_session)) -> List[ItemOut]:
    try:
        res = await db.execute(select(ItemORM).order_by(ItemORM.id))
        items = res.scalars().all()
        return [ItemOut.model_validate(i) for i in items]

    except Exception as e:
        log.error("Failed to list items", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve items")


@router.get("/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, db: AsyncSession = Depends(get_session)) -> ItemOut:
    res = await db.execute(select(ItemORM).where(ItemORM.id == item_id))
    obj = res.scalar_one_or_none()

    if not obj:
        log.warning("Item not found", id=item_id)
        raise HTTPException(status_code=404, detail="Item not found")

    found = ItemOut.model_validate(obj)
    log.info("Item retrieved", id=found.id, name=found.name)
    return found


@router.put("/{item_id}", response_model=ItemOut)
async def update_item(item_id: int, payload: ItemIn, db: AsyncSession = Depends(get_session)) -> ItemOut:
    res = await db.execute(select(ItemORM).where(ItemORM.id == item_id))
    obj = res.scalar_one_or_none()

    if not obj:
        log.warning("Item not found for update", id=item_id)
        raise HTTPException(status_code=404, detail="Item not found")

    obj.name = payload.name
    obj.price = payload.price
    await db.commit()
    await db.refresh(obj)

    updated = ItemOut.model_validate(obj)
    log.info("Item updated", id=updated.id, name=updated.name, price=updated.price)
    return updated


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, db: AsyncSession = Depends(get_session)) -> None:
    res = await db.execute(select(ItemORM).where(ItemORM.id == item_id))
    obj = res.scalar_one_or_none()

    if not obj:
        log.warning("Item not found for deletion", id=item_id)
        raise HTTPException(status_code=404, detail="Item not found")

    await db.delete(obj)
    await db.commit()

    log.info("Item deleted", id=item_id)
