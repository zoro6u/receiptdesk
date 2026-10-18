from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from .config import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()
