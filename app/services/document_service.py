"""Turn pasted text, PDFs and images into plain text. Uploads only ever touch a private temp dir."""
import io
import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile

from ..config import Settings
from ..errors import AppError

log = logging.getLogger("receiptdesk.documents")

ALLOWED = {".pdf": "pdf", ".png": "image", ".jpg": "image", ".jpeg": "image"}
MIN_TEXT_CHARS = 40  # below this a PDF is treated as scanned
MAX_IMAGE_PIXELS = 40_000_000

FEDORA_OCR_HELP = [
    "Install on Fedora: sudo dnf install tesseract tesseract-langpack-eng",
    "Other languages: sudo dnf install tesseract-langpack-fra (etc.), then set OCR_LANGUAGES=eng+fra",
]


def sniff_kind(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return None


def ocr_status(settings: Settings) -> tuple[bool, str | None]:
    """(available, problem). Never pretends OCR works."""
    try:
        import pytesseract
    except ImportError:  # pragma: no cover
        return False, "The pytesseract Python package is not installed."
    if shutil.which(getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")) is None:
        return False, "The Tesseract OCR program is not installed."
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return False, "Tesseract is installed but could not be run."
    missing = [l for l in settings.ocr_languages.split("+") if l and l not in installed]
    if missing:
        return False, f"Tesseract language data missing: {', '.join(missing)}."
    return True, None


def require_ocr(settings: Settings) -> None:
    ok, problem = ocr_status(settings)
    if not ok:
        raise AppError(503, "ocr_unavailable",
                       f"OCR is needed for this document but is unavailable. {problem}", FEDORA_OCR_HELP)


def _ocr_image(img, settings: Settings) -> str:
    import pytesseract
    try:
        return pytesseract.image_to_string(img, lang=settings.ocr_languages, timeout=60)
    except RuntimeError:
        raise AppError(504, "ocr_timeout", "OCR took too long on this document.")
    except Exception:
        raise AppError(422, "ocr_failed", "OCR could not read this document.")


async def save_upload(upload: UploadFile, tmpdir: Path, settings: Settings) -> tuple[Path, str]:
    """Validate and stream the upload into tmpdir under a generated name. Returns (path, 'pdf'|'image')."""
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise AppError(415, "unsupported_type", "Unsupported file type. Upload a PDF, PNG or JPG.")
    limit = settings.max_upload_mb * 1024 * 1024
    dest = tmpdir / f"upload{ext}"  # user-supplied filename is never used
    size, head = 0, b""
    with dest.open("wb") as f:
        while chunk := await upload.read(1024 * 1024):
            if not head:
                head = chunk[:16]
            size += len(chunk)
            if size > limit:
                raise AppError(413, "file_too_large", f"File is larger than the {settings.max_upload_mb} MB limit.")
            f.write(chunk)
    if size == 0:
        raise AppError(422, "empty_document", "The uploaded file is empty.")
    sniffed = sniff_kind(head)
    expected = "pdf" if ext == ".pdf" else ("png" if ext == ".png" else "jpg")
    if sniffed != expected:
        raise AppError(415, "content_mismatch", "The file content does not match its extension.")
    return dest, ALLOWED[ext]


def text_from_pdf(path: Path, settings: Settings) -> tuple[str, bool, list[str]]:
    """Returns (text, ocr_used, warnings)."""
    import pymupdf as fitz
    warnings: list[str] = []
    try:
        doc = fitz.open(path)
    except Exception:
        raise AppError(422, "unreadable_document", "This PDF could not be opened. It may be corrupted.")
    try:
        if doc.needs_pass:
            raise AppError(422, "encrypted_pdf", "Password-protected PDFs are not supported.")
        n = min(doc.page_count, settings.max_pdf_pages)
        if doc.page_count > n:
            warnings.append(f"Only the first {n} of {doc.page_count} pages were processed.")
        text = "\n".join(doc[i].get_text() for i in range(n)).strip()
        if len(text) >= MIN_TEXT_CHARS:
            return text, False, warnings
        # Scanned PDF: render pages and OCR them.
        require_ocr(settings)
        from PIL import Image
        parts = []
        for i in range(n):
            pix = doc[i].get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            parts.append(_ocr_image(img, settings))
        return "\n".join(parts).strip(), True, warnings
    except AppError:
        raise
    except Exception:
        raise AppError(422, "unreadable_document", "This PDF could not be read.")
    finally:
        doc.close()


def text_from_image(path: Path, settings: Settings) -> str:
    require_ocr(settings)
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(path) as img:
            img.load()
            return _ocr_image(img, settings).strip()
    except AppError:
        raise
    except Exception:
        raise AppError(422, "unreadable_document", "This image could not be read.")


async def extract_text(upload: UploadFile, settings: Settings) -> tuple[str, str, bool, list[str]]:
    """Returns (text, source_type, ocr_used, warnings). Temp files are always removed."""
    with tempfile.TemporaryDirectory(prefix="receiptdesk-") as d:
        path, kind = await save_upload(upload, Path(d), settings)
        if kind == "pdf":
            text, ocr_used, warnings = text_from_pdf(path, settings)
        else:
            text, ocr_used, warnings = text_from_image(path, settings), True, []
    if len(text.strip()) < 10:
        raise AppError(422, "no_text_found", "No readable text was found in this document.",
                       ["For scans, use a sharper, well-lit, upright image.", "You can also paste the text instead."])
    if ocr_used:
        warnings.append("Text came from OCR and may contain misread characters. Compare each field with the original.")
    return text, kind, ocr_used, warnings
