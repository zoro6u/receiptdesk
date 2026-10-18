import csv
import io
from typing import Iterable

from ..models import Expense

COLUMNS = ["id", "invoice_date", "supplier", "invoice_number", "currency", "subtotal", "tax", "total",
           "category", "notes", "source_type", "created_at", "updated_at"]
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def neutralize(value: str) -> str:
    """Prefix a quote so spreadsheets treat user text as text, never as a formula."""
    return "'" + value if value and value.startswith(_DANGEROUS) else value


def _money(v) -> str:
    return "" if v is None else format(v, "f")  # exact; numbers are never treated as text-to-neutralize


def to_csv(expenses: Iterable[Expense]) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for e in expenses:
        w.writerow([
            e.id,
            e.invoice_date.isoformat() if e.invoice_date else "",
            neutralize(e.supplier or ""),
            neutralize(e.invoice_number or ""),
            e.currency or "",
            _money(e.subtotal), _money(e.tax), _money(e.total),
            neutralize(e.category or ""),
            neutralize(e.notes or ""),
            e.source_type,
            e.created_at.isoformat(timespec="seconds") if e.created_at else "",
            e.updated_at.isoformat(timespec="seconds") if e.updated_at else "",
        ])
    return buf.getvalue()
