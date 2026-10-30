from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMBLOB, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base


class IdempotencyORM(Base):
    __tablename__ = 'request_idempotency'
    __table_args__ = (Index('ix_request_idempotency_expiry', 'state', 'expires_at'),)

    scope_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(256))
    caller_scope: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(128))
    route: Mapped[str] = mapped_column(String(512))
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    response_status: Mapped[int | None] = mapped_column(SMALLINT(unsigned=True))
    response_body: Mapped[bytes | None] = mapped_column(MEDIUMBLOB)
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
