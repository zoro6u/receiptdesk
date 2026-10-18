import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, MoneyType, UTCDateTime


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    supplier: Mapped[str] = mapped_column(String(300), index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True, index=True)
    subtotal: Mapped[Decimal | None] = mapped_column(MoneyType, nullable=True)
    tax: Mapped[Decimal | None] = mapped_column(MoneyType, nullable=True)
    total: Mapped[Decimal] = mapped_column(MoneyType)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now)
