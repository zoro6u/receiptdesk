"""Pydantic schemas. Money is Decimal end to end; JSON output renders it as a string."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_serializer, field_validator

MAX_MONEY = Decimal("999999999999.99")


class SourceType(str, Enum):
    text = "text"
    pdf = "pdf"
    image = "image"


def parse_money(value: Any) -> Decimal | None:
    """Convert model/user output to Decimal. Blank/None -> None. Garbage -> ValueError."""
    if value is None or isinstance(value, bool):
        if isinstance(value, bool):
            raise ValueError("amount must be a number")
        return None
    if isinstance(value, float):
        value = repr(value)
    if isinstance(value, (int, Decimal)):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("amount must be a number")
    s = value.strip().replace(" ", "").replace(" ", "")
    if s == "" or s.lower() in ("null", "none", "n/a"):
        return None
    # Accept "1,234.50" and "1234.50". Reject ambiguous things like "1.234,50" rather than guess.
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        raise ValueError(f"'{value}' is not a valid amount")
    try:
        d = Decimal(s)
    except InvalidOperation as e:  # pragma: no cover
        raise ValueError("invalid amount") from e
    if abs(d) > MAX_MONEY:
        raise ValueError("amount is too large")
    return d


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("date must be in YYYY-MM-DD format")
        return date.fromisoformat(v)  # raises ValueError for e.g. 2025-02-30
    raise ValueError("date must be a string")


def _blank_to_none(v: Any) -> Any:
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


Money = Annotated[Decimal | None, BeforeValidator(parse_money)]
OptDate = Annotated[date | None, BeforeValidator(parse_date)]
OptStr = Annotated[str | None, BeforeValidator(_blank_to_none)]


class _MoneyOut(BaseModel):
    @field_serializer("subtotal", "tax", "total", check_fields=False)
    def _ser_money(self, v: Decimal | None):
        return None if v is None else format(v, "f")


class ExpenseFields(_MoneyOut):
    """Fields shared by create/update/read."""
    supplier: Annotated[str, Field(min_length=1, max_length=300)]
    invoice_number: OptStr = None
    invoice_date: OptDate = None
    currency: OptStr = None
    subtotal: Money = None
    tax: Money = None
    total: Money = None
    category: OptStr = None
    notes: OptStr = None

    @field_validator("supplier", mode="before")
    @classmethod
    def _supplier(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("invoice_number", "category", "notes")
    @classmethod
    def _lengths(cls, v, info):
        limit = {"invoice_number": 100, "category": 100, "notes": 5000}[info.field_name]
        if v is not None and len(v) > limit:
            raise ValueError(f"must be at most {limit} characters")
        return v

    @field_validator("currency")
    @classmethod
    def _currency(cls, v):
        if v is None:
            return v
        v = v.upper()
        if not re.fullmatch(r"[A-Z]{3}", v):
            raise ValueError("currency must be a 3-letter code such as RWF, USD or EUR")
        return v

    @field_validator("subtotal", "tax", "total")
    @classmethod
    def _non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("amount cannot be negative")
        return v


class ExpenseCreate(ExpenseFields):
    total: Money = None
    source_type: SourceType = SourceType.text

    @field_validator("total")
    @classmethod
    def _total_required(cls, v):
        if v is None:
            raise ValueError("total is required before an expense can be saved")
        return v


class ExpenseUpdate(ExpenseCreate):
    pass


class ExpenseRead(ExpenseFields):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_type: SourceType
    created_at: datetime
    updated_at: datetime


class ExpenseList(BaseModel):
    items: list[ExpenseRead]
    total_count: int
    page: int
    page_size: int
    totals_by_currency: dict[str, str]


# ---- extraction ----

class RawExtraction(_MoneyOut):
    """What we accept from the model. Lenient on shape, strict on values: bad values become
    warnings in the service layer, they are never coerced to something plausible."""
    model_config = ConfigDict(extra="ignore")
    supplier: Any = None
    invoice_number: Any = None
    invoice_date: Any = None
    currency: Any = None
    subtotal: Any = None
    tax: Any = None
    total: Any = None


class ExtractedInvoice(_MoneyOut):
    supplier: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None


class ExtractTextRequest(BaseModel):
    text: Annotated[str, Field(min_length=1)]


class ExtractionResult(BaseModel):
    fields: ExtractedInvoice
    warnings: list[str]
    source_type: SourceType
    text_preview: str | None = None
    model: str
    ocr_used: bool = False
