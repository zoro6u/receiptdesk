import csv
import io

import pytest

from app.services.csv_service import COLUMNS, neutralize

BASE = {"supplier": "Acme", "total": "10.50", "currency": "RWF", "source_type": "text"}


def fetch(client, **params):
    r = client.get("/api/expenses/export.csv", params=params)
    assert r.status_code == 200
    return r, list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))


def test_headers_and_response_metadata(client):
    r, rows = fetch(client)
    assert rows == [COLUMNS]
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"].startswith('attachment; filename="receiptdesk-expenses-')
    assert r.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel


def test_rows_roundtrip_with_commas_quotes_newlines_and_unicode(client):
    tricky = 'Café "Le, Petit"\nsecond line'
    client.post("/api/expenses", json={**BASE, "supplier": tricky, "notes": "a,b\r\nc \"q\" é", "invoice_date": "2025-09-18",
                                       "invoice_number": "N1", "subtotal": "10", "tax": "0.50"})
    _, rows = fetch(client)
    rec = dict(zip(rows[0], rows[1]))
    assert len(rows) == 2
    assert rec["supplier"] == tricky and rec["notes"] == "a,b\r\nc \"q\" é"
    assert rec["invoice_date"] == "2025-09-18" and rec["currency"] == "RWF"
    assert (rec["subtotal"], rec["tax"], rec["total"]) == ("10", "0.50", "10.50")


def test_missing_optionals_are_empty_cells(client):
    client.post("/api/expenses", json={"supplier": "X", "total": "1"})
    _, rows = fetch(client)
    rec = dict(zip(rows[0], rows[1]))
    for k in ("invoice_date", "invoice_number", "currency", "subtotal", "tax", "category", "notes"):
        assert rec[k] == ""


@pytest.mark.parametrize("val", ["=SUM(A1)", "+1+1", "-2+3", "@cmd", "=HYPERLINK(\"http://x\")"])
def test_formula_injection_neutralized(client, val):
    client.post("/api/expenses", json={**BASE, "supplier": val, "invoice_number": val, "category": val, "notes": val})
    _, rows = fetch(client)
    rec = dict(zip(rows[0], rows[1]))
    for k in ("supplier", "invoice_number", "category", "notes"):
        assert rec[k] == "'" + val


def test_neutralize_covers_tab_and_cr_prefixes():
    assert neutralize("\t=1") == "'\t=1" and neutralize("\r=1") == "'\r=1"


def test_neutralize_leaves_normal_text():
    assert neutralize("Acme") == "Acme" and neutralize("") == "" and neutralize("a=b") == "a=b"


def test_currencies_never_combined_and_filters_apply(client):
    client.post("/api/expenses", json={**BASE, "supplier": "A"})
    client.post("/api/expenses", json={**BASE, "supplier": "B", "currency": "USD"})
    _, rows = fetch(client)
    assert sorted((r[COLUMNS.index("supplier")], r[COLUMNS.index("currency")]) for r in rows[1:]) == [("A", "RWF"), ("B", "USD")]
    _, rows = fetch(client, currency="USD")
    assert [r[COLUMNS.index("supplier")] for r in rows[1:]] == ["B"]
    _, rows = fetch(client, q="nomatch")
    assert len(rows) == 1


def test_export_selected_ids(client):
    a = client.post("/api/expenses", json={**BASE, "supplier": "A"}).json()["id"]
    client.post("/api/expenses", json={**BASE, "supplier": "B"})
    _, rows = fetch(client, ids=a)
    assert [r[COLUMNS.index("supplier")] for r in rows[1:]] == ["A"]
