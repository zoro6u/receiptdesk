import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import models  # noqa: F401  (register tables)
from .config import Settings, get_settings
from .database import Base, make_engine, make_session_factory
from .errors import install_error_handlers
from .routers import expenses, extraction, health

APP_DIR = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="ReceiptDesk", version="0.1.0")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    install_error_handlers(app)

    for r in (health.router, extraction.router, expenses.router):
        app.include_router(r)
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=APP_DIR / "templates")

    def page(name: str, active: str):
        def handler(request: Request):
            return templates.TemplateResponse(request, name, {
                "active": active, "max_upload_mb": settings.max_upload_mb, "model": settings.ollama_model,
                "max_pdf_pages": settings.max_pdf_pages})
        return handler

    app.add_api_route("/", page("dashboard.html", "dashboard"), include_in_schema=False)
    app.add_api_route("/extract", page("extract.html", "extract"), include_in_schema=False)
    app.add_api_route("/expenses", page("expenses.html", "expenses"), include_in_schema=False)
    return app


app = create_app()
