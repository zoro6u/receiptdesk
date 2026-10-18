from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..config import Settings
from ..deps import get_app_settings
from ..errors import AppError
from ..schemas import ExtractionResult, ExtractTextRequest, SourceType
from ..services import document_service, ollama_service

router = APIRouter(prefix="/api/extract", tags=["extraction"])
PREVIEW_CHARS = 1500


def _preview(text: str) -> str:
    return text[:PREVIEW_CHARS] + ("…" if len(text) > PREVIEW_CHARS else "")


@router.post("/text", response_model=ExtractionResult)
def extract_text(req: ExtractTextRequest, settings: Settings = Depends(get_app_settings)):
    text = req.text.strip()
    if len(text) < 10:
        raise AppError(422, "no_text_found", "Please paste the invoice text (at least a few words).")
    fields, warnings = ollama_service.extract_invoice(text, settings)
    return ExtractionResult(fields=fields, warnings=warnings, source_type=SourceType.text,
                            model=settings.ollama_model)


@router.post("/file", response_model=ExtractionResult)
async def extract_file(file: UploadFile = File(...), settings: Settings = Depends(get_app_settings)):
    text, kind, ocr_used, doc_warnings = await document_service.extract_text(file, settings)
    fields, warnings = await run_in_threadpool(ollama_service.extract_invoice, text, settings)
    return ExtractionResult(
        fields=fields, warnings=doc_warnings + warnings, source_type=SourceType(kind),
        text_preview=_preview(text) if ocr_used else None, model=settings.ollama_model, ocr_used=ocr_used,
    )
