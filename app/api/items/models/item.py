from pydantic import BaseModel, Field


class Item(BaseModel):
    id: int = Field(..., description="Unique identifier for the item.")
    name: str = Field(..., description="Item name.")
    price: float = Field(..., ge=0, description="Item price in currency units.")

    class Config:
        from_attributes = True
