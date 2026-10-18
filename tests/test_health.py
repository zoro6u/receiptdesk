import httpx


def test_health_reports_app_and_ollama_separately(client, fake_ollama):
    fake_ollama(lambda req: httpx.Response(200, json={"models": [{"name": "gemma3:4b"}]}))
    body = client.get("/api/health").json()
    assert body["app"]["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["ollama"] == {"status": "ok", "model": "gemma3:4b", "model_available": True, "detail": None}


def test_health_app_ok_when_ollama_down(client, fake_ollama):
    def boom(req):
        raise httpx.ConnectError("refused")
    fake_ollama(boom)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ollama"]["status"] == "unavailable"
    assert "ollama serve" in r.json()["ollama"]["detail"]


def test_health_model_missing(client, fake_ollama):
    fake_ollama(lambda req: httpx.Response(200, json={"models": [{"name": "llama3:8b"}]}))
    o = client.get("/api/health").json()["ollama"]
    assert o["status"] == "model_missing" and "ollama pull gemma3:4b" in o["detail"]


def test_pages_render(client):
    for p in ("/", "/extract", "/expenses"):
        assert client.get(p).status_code == 200
