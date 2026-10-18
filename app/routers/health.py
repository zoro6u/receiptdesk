from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_app_settings, get_db
from ..services import document_service, ollama_service

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)):
    """App/database status is reported separately from Ollama and OCR, which are optional at runtime."""
    try:
        db.execute(text("SELECT 1"))
        database = {"status": "ok"}
    except Exception:
        database = {"status": "error"}
    ocr_ok, ocr_problem = document_service.ocr_status(settings)
    body = {
        "app": {"status": "ok"},
        "database": database,
        "ollama": ollama_service.check_ollama(settings),
        "ocr": {"status": "ok" if ocr_ok else "unavailable", "detail": ocr_problem},
    }
    return JSONResponse(body, status_code=200 if database["status"] == "ok" else 503)
