import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        ollama_base_url="http://ollama.test", ollama_model="gemma3:4b",
        database_url=f"sqlite:///{tmp_path / 'test.db'}", max_upload_mb=1, ollama_timeout_s=5, ollama_keep_alive="30m", ollama_num_gpu=None,
        max_pdf_pages=3, ocr_languages="eng", max_text_chars=20000,
    )


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


@pytest.fixture
def fake_ollama(monkeypatch):
    """Route all Ollama HTTP calls to a handler: fake_ollama(lambda request: httpx.Response(...))."""
    from app.services import ollama_service

    def install(handler):
        def factory(settings, timeout=None):
            return httpx.Client(base_url=settings.ollama_base_url, transport=httpx.MockTransport(handler))
        monkeypatch.setattr(ollama_service, "_client", factory)
    return install


def chat_reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})
