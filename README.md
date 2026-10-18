# ReceiptDesk

**Local-first receipt and invoice extractor for freelancers and small businesses** (built with Rwanda and RWF in mind, works with any currency).
Paste invoice text or upload a PDF/photo, let a local **Gemma** model suggest the fields, review and correct them, save to SQLite, and export CSV for Excel or Google Sheets.

Built for the Hacktoberfest Open-Source AI Challenge, Week 2: Side Hustle. Licensed under MIT (a permissive default; no other requirement applied).

## What it does

- **Input**: pasted text, text-based PDFs (PyMuPDF), scanned PDFs and PNG/JPG images (Tesseract OCR).
- **Extraction**: Gemma via the Ollama HTTP API returns `supplier, invoice_number, invoice_date, currency, subtotal, tax, total` as JSON. The prompt tells the model to use `null` instead of guessing and to treat the document as untrusted data.
- **Checks, not trust**: output is validated with Pydantic and deterministic rules. Problems are shown as **warnings and never silently fixed**: invalid dates or amounts (left blank), negative amounts, `subtotal + tax ≠ total`, and amounts that do not literally appear in the document text.
- **Human review**: nothing is saved until you press *Confirm and save*. Total and supplier are required.
- **Expenses table**: search (supplier / invoice number), currency and date filters, sorting, pagination, edit, delete with confirmation.
- **CSV export**: all, filtered, or selected rows. UTF-8 with BOM, stable headers, spreadsheet formula-injection protection.
- **Money** is handled as `Decimal` and stored as exact text in SQLite. Totals are always grouped per currency, never summed across currencies.

## Setup on Fedora

Requires Python 3.11+ (developed on 3.14).

```bash
# 1. System packages: Tesseract OCR (optional, needed for scans and images only)
sudo dnf install tesseract tesseract-langpack-eng

# 2. Python environment
cd receiptdesk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Ollama + Gemma (see https://ollama.com/download; use the official build, some distro packages stall on Gemma 3)
curl -fsSL https://ollama.com/install.sh | sh
ollama serve            # skip if the systemd service is already running
ollama pull gemma3:4b   # about 3 GB download

# 4. Optional configuration
cp .env.example .env

# 5. Run
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Try `samples/sample_invoice.txt` (fictional data) on the *Extract invoice* page.

Running on a laptop without a capable GPU? Set `OLLAMA_NUM_GPU=0` in `.env` to force CPU. In testing on a CPU-only run, extracting the sample invoice with `gemma3:4b` took roughly 35-45 seconds, and the first request after start-up is slower while the model loads.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `gemma3:4b` | Any Ollama model tag (e.g. `gemma3:12b`) |
| `DATABASE_URL` | `sqlite:///<project>/data/receiptdesk.db` | SQLAlchemy URL |
| `OLLAMA_NUM_GPU` | unset | `0` forces CPU only (fixes hangs on small/old GPUs) |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |
| `OLLAMA_TIMEOUT_S` | `600` | Model timeout (first load on a CPU-only machine can take minutes) |
| `OLLAMA_KEEP_ALIVE` | `30m` | How long Ollama keeps the model loaded after a request |
| `MAX_PDF_PAGES` | `5` | Pages processed per PDF |
| `OCR_LANGUAGES` | `eng` | Tesseract languages, e.g. `eng+fra` |

For more OCR languages install the matching pack, e.g. `sudo dnf install tesseract-langpack-fra`.

## Tests

```bash
source .venv/bin/activate
python -m pytest
```

Tests need no Ollama, no model, no internet and no Tesseract. Ollama is replaced by `httpx.MockTransport`, OCR availability is simulated, and every test uses a temporary SQLite file.

## Architecture and data flow

```
Browser (HTML/CSS/JS)  ──►  FastAPI  ──►  document_service  (PyMuPDF / Tesseract, temp dir, deleted after use)
                                     ──►  ollama_service    (HTTP to local Ollama → Gemma)  ──►  validation.py (warnings)
                                     ──►  SQLite via SQLAlchemy (only after the user confirms)
```

1. `POST /api/extract/text` or `/api/extract/file` → text is obtained → Gemma suggests fields → validation adds warnings → response. **Nothing is stored.**
2. The user edits the form and confirms → `POST /api/expenses` → SQLite.
3. `GET /api/expenses/export.csv` (accepts the same filters as the list, plus `ids=`).

Other endpoints: `GET /api/health` (app and database reported separately from Ollama and OCR), `GET/PUT/DELETE /api/expenses/{id}`, `GET /api/expenses/summary`. Errors use one format: `{"error": {"code", "message", "details"}}`. Interactive docs at `/docs`.

Layout: `app/routers/` (HTTP), `app/services/` (Ollama, documents, validation, CSV), `app/schemas.py` (validation and money parsing), `app/templates` + `app/static` (UI), `tests/`.

### What is processed where, and what is retained

- All processing happens on your machine: Ollama (Gemma), Tesseract and SQLite. The app makes no other network calls. If you point `OLLAMA_BASE_URL` at a remote server, document text goes there.
- Uploaded files are streamed into a private temporary directory under a generated name, never the original filename, and deleted when processing ends, also on errors. **They are not retained.** Only the fields you confirm are saved (not the document text or OCR output).
- Invoice contents and OCR output are not logged. The OCR text preview is shown only for scans, and only in the review step.

## Security and privacy limitations

No authentication: the app is meant for a single user on `localhost`. Do not expose it to a network as is. The SQLite file is **not encrypted**. File validation checks extension, magic bytes and size, but PDFs and images are still parsed by PyMuPDF/Pillow/Tesseract, so keep those updated. Prompt-injection defences (delimiters, instructions, validation, human review) reduce but cannot eliminate the risk of manipulated output, which is why review is mandatory. No claim of absolute privacy or security is made. A full review is still outstanding.

## Current limitations

- Small local models make mistakes, especially on messy OCR text; always compare with the original. Handwriting, low-quality scans and non-Latin scripts are poorly supported. Ambiguous dates (03/04/2025) are deliberately left blank.
- One document at a time; no batching, no line items, no multi-currency conversion, no automatic categorisation.
- Scanned PDFs: only the first `MAX_PDF_PAGES` pages are read.
- The first request after Ollama starts is slow while the model loads.
- Extraction quality with real Gemma has not been benchmarked (see below).
- Image-only input goes through OCR, not through Gemma's vision. Switching to a multimodal path is a future option.

Ideas: batch import, line items, categories suggestions, receipts folder watcher, XLSX export, multilingual prompts (Kinyarwanda/French), an accuracy benchmark set.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Gemma never loads ("progress 0.00" in the Ollama log) | Update Ollama with the official installer; distro-packaged builds can stall on Gemma 3 |
| "Cannot reach Ollama" | `ollama serve` (or `systemctl start ollama`); check `OLLAMA_BASE_URL` |
| "Model … is not available" | `ollama pull gemma3:4b` (or set `OLLAMA_MODEL` to a model you have) |
| Requests hang or crawl on a laptop with a small NVIDIA GPU | Set `OLLAMA_NUM_GPU=0` to run on CPU only |
| "took too long" | Wait and retry (model loading), raise `OLLAMA_TIMEOUT_S`, or use a smaller model |
| "OCR is needed … unavailable" | `sudo dnf install tesseract tesseract-langpack-eng` |
| "Tesseract language data missing" | Install the langpack for each code in `OCR_LANGUAGES` |
| "did not return valid structured data" | Retry; try a larger model; fill the form manually |
| Port in use | `uvicorn app.main:app --port 8001` |

`GET /api/health` shows the status of the database, Ollama and OCR.

## Recording a 60-90 second demo

1. Start Ollama and the app; open the dashboard (show the empty state, or a few saved records).
2. *Extract invoice* → paste `samples/sample_invoice.txt` → *Extract with Gemma* (about 15 s; speed up in editing).
3. Show the filled form and any warnings; fix a value; *Confirm and save*.
4. On *Expenses*: search by supplier, sort by amount, edit a row, delete one (confirmation).
5. Click *Export CSV* and open it in a spreadsheet.
6. End on the footer note: local model, nothing uploaded, files deleted after processing.

Record with GNOME's built-in screen recorder (`Ctrl+Shift+Alt+R`) or OBS.
