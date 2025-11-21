from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base


class ItemORM(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Primary key identifier for the item.",
    )

    name: Mapped[str] = mapped_column(
        String(120),
        index=True,
        nullable=False,
        doc="Descriptive name of the item (max length 120).",
    )

    price: Mapped[float] = mapped_column(
        Float, nullable=False, doc="Price of the item stored as a floating-point value."
    )
