from pydantic import BaseModel, Field


class Item(BaseModel):
    id: int = Field(..., description="Unique identifier for the item.")
    name: str = Field(..., description="Item name.")
    price: float = Field(..., ge=0, description="Item price in currency units.")

    class Config:
        from_attributes = True


class ItemIn(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=120, description="Name of the item."
    )
    price: float = Field(..., ge=0, description="Item price in currency units.")

    class Config:
        from_attributes = True


class ItemOut(BaseModel):
    id: int = Field(..., description="Unique identifier for the item.")
    name: str = Field(..., description="Name of the item.")
    price: float = Field(..., ge=0, description="Item price in currency units.")

    class Config:
        from_attributes = True
