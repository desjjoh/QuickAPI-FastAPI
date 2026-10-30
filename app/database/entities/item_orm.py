from decimal import Decimal

from sqlalchemy import Numeric, String, Text
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.database.entities.base_orm import BaseEntity


class ItemORM(BaseEntity):
    __tablename__ = "items"

    version: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False, default=1, server_default='1'
    )

    name: Mapped[str] = mapped_column(
        String(120),
        index=True,
        nullable=False,
        doc="Descriptive name of the item (max length 120).",
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        doc="Price of the item represented as a decimal with 2 fractional digits.",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional free-text description of the item; null when not provided.",
    )
