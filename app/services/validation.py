"""Deterministic checks on model output. Problems become warnings; values are never rewritten
to make them look right."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..schemas import ExtractedInvoice, RawExtraction, parse_date, parse_money

LABELS = {
    "supplier": "Supplier", "invoice_number": "Invoice number", "invoice_date": "Invoice date",
    "currency": "Currency", "subtotal": "Subtotal", "tax": "Tax", "total": "Total",
}
_NUM_TOKEN = re.compile(r"\d[\d.,\s]*\d|\d")


def _str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return None
    s = str(v).strip()
    return s or None


def _amounts_in_text(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for tok in _NUM_TOKEN.findall(text):
        tok = tok.strip().replace(" ", "")
        for cand in (tok.replace(",", ""), tok.replace(".", "").replace(",", ".")):
            try:
                found.add(Decimal(cand))
            except InvalidOperation:
                pass
    return found


def validate_extraction(raw: RawExtraction, source_text: str) -> tuple[ExtractedInvoice, list[str]]:
    warnings: list[str] = []
    out: dict[str, Any] = {}

    out["supplier"] = _str(raw.supplier)
    out["invoice_number"] = _str(raw.invoice_number)

    cur = _str(raw.currency)
    if cur is not None:
        cur = cur.upper()
        if not re.fullmatch(r"[A-Z]{3}", cur):
            warnings.append(f"Currency '{cur[:10]}' is not a 3-letter code, so it was left blank. Please set it manually.")
            cur = None
    out["currency"] = cur

    try:
        out["invoice_date"] = parse_date(raw.invoice_date if not isinstance(raw.invoice_date, (int, float, dict, list)) else str(raw.invoice_date))
    except ValueError:
        warnings.append(f"The model returned an invalid date ('{str(raw.invoice_date)[:20]}'), so the date was left blank.")
        out["invoice_date"] = None
    if out["invoice_date"] and not (date(1990, 1, 1) <= out["invoice_date"] <= date(2100, 1, 1)):
        warnings.append(f"Invoice date {out['invoice_date']} looks implausible. Please check it.")

    for name in ("subtotal", "tax", "total"):
        try:
            out[name] = parse_money(getattr(raw, name))
        except ValueError:
            warnings.append(f"{LABELS[name]} ('{str(getattr(raw, name))[:20]}') is not a valid amount, so it was left blank.")
            out[name] = None
        if out[name] is not None and out[name] < 0:
            warnings.append(f"{LABELS[name]} is negative ({out[name]}). Check whether this is a credit note; negative amounts cannot be saved.")

    inv = ExtractedInvoice(**out)

    for name in ("supplier", "total", "invoice_date", "currency"):
        if getattr(inv, name) is None:
            warnings.append(f"{LABELS[name]} was not found. Please fill it in if it appears on the document.")

    if inv.subtotal is not None and inv.tax is not None and inv.total is not None:
        expected = inv.subtotal + inv.tax
        if expected != inv.total:
            warnings.append(
                f"Totals do not add up: subtotal {inv.subtotal} + tax {inv.tax} = {expected}, but total is {inv.total}. "
                "Nothing was changed; check the document (discounts or rounding may explain it)."
            )

    # Grounding check: amounts should literally appear in the source document.
    if source_text:
        present = _amounts_in_text(source_text)
        for name in ("subtotal", "tax", "total"):
            v = getattr(inv, name)
            if v is not None and v not in present:
                warnings.append(f"{LABELS[name]} {v} was not found as a number in the document text. It may be a mistake, verify it.")
    return inv, warnings
