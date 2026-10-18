"""Runtime configuration, read from environment variables (and an optional .env file)."""
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no extra dependency). Real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    ollama_model: str
    database_url: str
    max_upload_mb: int
    ollama_timeout_s: float
    ollama_keep_alive: str
    ollama_num_gpu: int | None  # None = let Ollama decide; 0 = force CPU only
    max_pdf_pages: int
    ocr_languages: str
    max_text_chars: int


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "gemma3:4b"),
        database_url=os.environ.get("DATABASE_URL", f"sqlite:///{data_dir / 'receiptdesk.db'}"),
        max_upload_mb=int(os.environ.get("MAX_UPLOAD_MB", "10")),
        ollama_timeout_s=float(os.environ.get("OLLAMA_TIMEOUT_S", "600")),
        ollama_keep_alive=os.environ.get("OLLAMA_KEEP_ALIVE", "30m"),
        ollama_num_gpu=int(os.environ["OLLAMA_NUM_GPU"]) if os.environ.get("OLLAMA_NUM_GPU", "").strip() else None,
        max_pdf_pages=int(os.environ.get("MAX_PDF_PAGES", "5")),
        ocr_languages=os.environ.get("OCR_LANGUAGES", "eng"),
        max_text_chars=int(os.environ.get("MAX_TEXT_CHARS", "20000")),
    )
