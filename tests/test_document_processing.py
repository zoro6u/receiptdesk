import io
import json

import pymupdf
import pytest
from PIL import Image

from app.services import document_service
from tests.conftest import chat_reply

INVOICE = "Kigali Print Ltd\nInvoice No: KPD-1\nDate: 2025-09-18\nSubtotal 100\nTax 18\nTOTAL 118 RWF\n"
REPLY = json.dumps({"supplier": "Kigali Print Ltd", "invoice_number": "KPD-1", "invoice_date": "2025-09-18",
                    "currency": "RWF", "subtotal": 100, "tax": 18, "total": 118})


def make_pdf(text=None, pages=1):
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, "PNG")
    return buf.getvalue()


def upload(client, name, data, ctype="application/octet-stream"):
    return client.post("/api/extract/file", files={"file": (name, data, ctype)})


def test_text_pdf_extraction(client, fake_ollama):
    fake_ollama(lambda r: chat_reply(REPLY))
    r = upload(client, "inv.pdf", make_pdf(INVOICE), "application/pdf")
    assert r.status_code == 200
    body = r.json()
    assert body["source_type"] == "pdf" and body["ocr_used"] is False and body["text_preview"] is None
    assert body["fields"]["total"] == "118"


def test_pdf_page_limit(client, fake_ollama):
    fake_ollama(lambda r: chat_reply(REPLY))
    body = upload(client, "inv.pdf", make_pdf(INVOICE, pages=6)).json()
    assert any("first 3 of 6 pages" in w for w in body["warnings"])


@pytest.mark.parametrize("name", ["evil.exe", "notes.txt", "x.svg", "noext", "x.pdf.sh", "x.gif"])
def test_unsupported_types(client, name):
    r = upload(client, name, b"hello")
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_type"


def test_content_must_match_extension(client):
    r = upload(client, "fake.pdf", b"MZ\x90\x00 this is an exe")
    assert r.status_code == 415 and r.json()["error"]["code"] == "content_mismatch"
    r = upload(client, "fake.png", make_pdf(INVOICE))
    assert r.status_code == 415


def test_empty_file(client):
    r = upload(client, "a.pdf", b"")
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_document"


def test_corrupted_pdf(client):
    r = upload(client, "a.pdf", b"%PDF-1.4 garbage garbage not really a pdf")
    assert r.status_code == 422 and r.json()["error"]["code"] in ("unreadable_document", "ocr_unavailable", "no_text_found")


def test_oversized_upload(client):  # limit is 1 MB in test settings
    r = upload(client, "big.pdf", b"%PDF-" + b"0" * (1024 * 1024 + 10))
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


@pytest.fixture
def no_tesseract(monkeypatch):
    monkeypatch.setattr(document_service.shutil, "which", lambda *_: None)


def test_image_without_ocr_is_reported_honestly(client, no_tesseract, fake_ollama):
    called = []
    fake_ollama(lambda r: called.append(1) or chat_reply(REPLY))
    r = upload(client, "scan.png", png_bytes())
    err = r.json()["error"]
    assert r.status_code == 503 and err["code"] == "ocr_unavailable"
    assert any("sudo dnf install tesseract" in d for d in err["details"])
    assert not called  # Gemma was never asked to "extract" from nothing


def test_scanned_pdf_without_ocr(client, no_tesseract):
    r = upload(client, "scan.pdf", make_pdf(None))  # blank page: no text layer
    assert r.status_code == 503 and r.json()["error"]["code"] == "ocr_unavailable"


def test_missing_language_data(monkeypatch, settings):
    import pytesseract
    monkeypatch.setattr(document_service.shutil, "which", lambda *_: "/usr/bin/tesseract")
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["osd"])
    ok, problem = document_service.ocr_status(settings)
    assert not ok and "eng" in problem


def test_image_with_ocr_available(client, monkeypatch, fake_ollama):
    monkeypatch.setattr(document_service, "ocr_status", lambda s: (True, None))
    monkeypatch.setattr(document_service, "_ocr_image", lambda img, s: INVOICE)
    fake_ollama(lambda r: chat_reply(REPLY))
    body = upload(client, "scan.JPG", b"\xff\xd8\xff\xe0" + b"0" * 100).json() if False else None
    buf = io.BytesIO(); Image.new("RGB", (40, 40), "white").save(buf, "JPEG")
    body = upload(client, "scan.JPG", buf.getvalue()).json()
    assert body["source_type"] == "image" and body["ocr_used"] is True
    assert "Kigali" in body["text_preview"]
    assert any("OCR" in w for w in body["warnings"])
    assert body["fields"]["total"] == "118"


def test_ocr_returning_nothing_is_an_error(client, monkeypatch):
    monkeypatch.setattr(document_service, "ocr_status", lambda s: (True, None))
    monkeypatch.setattr(document_service, "_ocr_image", lambda img, s: "  ")
    r = upload(client, "blank.png", png_bytes())
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_text_found"


def test_temp_files_removed_even_on_error(client, monkeypatch, tmp_path):
    import tempfile
    seen = []
    real = tempfile.TemporaryDirectory

    class Spy(real):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            seen.append(self.name)
    monkeypatch.setattr(document_service.tempfile, "TemporaryDirectory", Spy)
    upload(client, "bad.pdf", b"%PDF-1.4 junk")
    upload(client, "x.pdf", make_pdf(INVOICE))
    from pathlib import Path
    assert seen and not any(Path(p).exists() for p in seen)


def test_user_filename_not_used_on_disk(client, monkeypatch):
    names = []
    orig = document_service.save_upload

    async def spy(upload, tmpdir, settings):
        path, kind = await orig(upload, tmpdir, settings)
        names.append(path.name)
        return path, kind
    monkeypatch.setattr(document_service, "save_upload", spy)
    upload(client, "../../etc/passwd.pdf", make_pdf(INVOICE))
    assert names == ["upload.pdf"]
