from datetime import datetime
from secrets import choice

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.config.database import Base


def generate_id() -> str:
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

    return ''.join(choice(alphabet) for _ in range(16))


class BaseEntity(Base):
    __abstract__ = True

    id: Mapped[str] = mapped_column(
        String(16),
        primary_key=True,
        default=generate_id,
        doc="Primary identifier for the entity (16 ASCII letters or digits).",
    )

    created_at: Mapped[datetime] = mapped_column(
        "createdAt",
        DateTime(timezone=True),
        server_default=func.now(),
        doc="Timestamp when the record was created (UTC).",
    )

    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        doc="Timestamp when the record was last updated (UTC).",
    )
