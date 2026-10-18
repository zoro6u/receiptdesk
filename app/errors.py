"""Consistent error format: {"error": {"code": str, "message": str, "details": [...]}}"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import logging

log = logging.getLogger("receiptdesk")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or []


def _body(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e["loc"] if p != "body")
            details.append(f"{loc}: {e['msg']}" if loc else e["msg"])  # never echo input values
        return JSONResponse(_body("validation_error", "Some fields are invalid.", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(_body("http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.error("Unhandled error: %s", type(exc).__name__)  # type only: never log content
        return JSONResponse(_body("internal_error", "Something went wrong on the server."), status_code=500)
