import pytest

BASE = {"supplier": "Kigali Print", "invoice_number": "INV-1", "invoice_date": "2025-09-18", "currency": "rwf",
        "subtotal": "115000", "tax": "20700", "total": "135700", "category": "Marketing", "source_type": "text"}


def create(client, **over):
    return client.post("/api/expenses", json={**BASE, **over})


def test_save_reviewed_expense(client):
    r = create(client)
    assert r.status_code == 201
    e = r.json()
    assert e["id"] and e["currency"] == "RWF" and e["total"] == "135700" and e["created_at"] and e["updated_at"]
    assert client.get(f"/api/expenses/{e['id']}").json()["supplier"] == "Kigali Print"


def test_optional_fields_stay_null(client):
    e = client.post("/api/expenses", json={"supplier": "Cafe", "total": "5.50", "invoice_date": "", "subtotal": "", "currency": ""}).json()
    assert e["invoice_date"] is None and e["subtotal"] is None and e["tax"] is None and e["currency"] is None
    assert e["invoice_number"] is None and e["source_type"] == "text"


def test_money_is_exact(client):
    e = create(client, total="0.1", subtotal="0.07", tax="0.03").json()
    assert e["total"] == "0.1"
    got = client.get(f"/api/expenses/{e['id']}").json()
    assert got["total"] == "0.1" and got["subtotal"] == "0.07"
    assert client.get("/api/expenses/summary").json()["totals_by_currency"] == {"RWF": "0.1"}


@pytest.mark.parametrize("over,field", [
    ({"total": None}, "total"), ({"total": ""}, "total"), ({"total": "-1"}, "total"), ({"total": "abc"}, "total"),
    ({"total": "1e5"}, "total"), ({"supplier": "  "}, "supplier"), ({"invoice_date": "2025-13-01"}, "invoice_date"),
    ({"invoice_date": "18/09/2025"}, "invoice_date"), ({"currency": "FRANCS"}, "currency"), ({"tax": "-2"}, "tax"),
    ({"source_type": "fax"}, "source_type"),
])
def test_invalid_values_rejected(client, over, field):
    r = create(client, **over)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and any(field in d for d in err["details"])


def test_list_search_filter_sort(client):
    create(client, supplier="Alpha Ltd", invoice_number="A-1", total="100", invoice_date="2025-01-10")
    create(client, supplier="Beta Co", invoice_number="B-77", total="2000", invoice_date="2025-03-10", currency="USD")
    create(client, supplier="100% Gamma_x", invoice_number="G", total="50", invoice_date="2025-02-10")
    def ids(**p):
        return [i["supplier"] for i in client.get("/api/expenses", params=p).json()["items"]]
    assert ids(q="alpha") == ["Alpha Ltd"]
    assert ids(q="b-77") == ["Beta Co"]
    assert ids(q="100%") == ["100% Gamma_x"]          # LIKE wildcards are escaped
    assert ids(q="%") == ["100% Gamma_x"]
    assert ids(currency="usd") == ["Beta Co"]
    assert ids(date_from="2025-02-01", date_to="2025-02-28") == ["100% Gamma_x"]
    assert ids(sort="date", order="asc") == ["Alpha Ltd", "100% Gamma_x", "Beta Co"]
    assert ids(sort="amount", order="desc") == ["Beta Co", "Alpha Ltd", "100% Gamma_x"]  # numeric, not text order
    body = client.get("/api/expenses").json()
    assert body["total_count"] == 3 and body["totals_by_currency"] == {"RWF": "150", "USD": "2000"}  # never mixed


def test_pagination(client):
    for i in range(5):
        create(client, supplier=f"S{i}")
    r = client.get("/api/expenses", params={"page": 2, "page_size": 2}).json()
    assert len(r["items"]) == 2 and r["total_count"] == 5 and r["page"] == 2
    assert client.get("/api/expenses", params={"page_size": 1000}).status_code == 422


def test_edit_expense(client):
    e = create(client).json()
    r = client.put(f"/api/expenses/{e['id']}", json={**BASE, "supplier": "Renamed", "total": "99.99", "source_type": "pdf"})
    assert r.status_code == 200
    got = r.json()
    assert got["supplier"] == "Renamed" and got["total"] == "99.99" and got["source_type"] == "text"  # source is immutable
    assert got["updated_at"] >= e["updated_at"] and got["created_at"] == e["created_at"]
    assert client.put(f"/api/expenses/{e['id']}", json={**BASE, "total": None}).status_code == 422


def test_delete_expense(client):
    e = create(client).json()
    assert client.delete(f"/api/expenses/{e['id']}").status_code == 204
    assert client.get(f"/api/expenses/{e['id']}").status_code == 404
    assert client.delete(f"/api/expenses/{e['id']}").status_code == 404
    assert client.get("/api/expenses/nope").json()["error"]["code"] == "not_found"


def test_summary(client):
    assert client.get("/api/expenses/summary").json()["most_used_currency"] is None
    create(client); create(client); create(client, currency="USD")
    s = client.get("/api/expenses/summary").json()
    assert s["count"] == 3 and s["most_used_currency"] == "RWF" and s["totals_by_currency"] == {"RWF": "271400", "USD": "135700"}


def test_html_in_fields_is_stored_verbatim_as_data(client):
    e = create(client, supplier="<script>alert(1)</script>").json()
    assert e["supplier"] == "<script>alert(1)</script>"  # escaping happens in the UI (textContent)


def test_ui_uses_no_innerhtml():
    from pathlib import Path
    js = (Path(__file__).parent.parent / "app/static/js/app.js").read_text()
    code = "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code
