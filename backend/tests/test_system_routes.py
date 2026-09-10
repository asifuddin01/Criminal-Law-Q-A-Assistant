from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_ok_without_touching_provider(monkeypatch):
    """Health must not depend on the model provider: an unreachable provider is
    not the same failure as a dead service."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_meta_reports_capabilities_for_ollama(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    from app.config import get_settings
    from app.llm.registry import get_provider

    get_settings.cache_clear()
    get_provider.cache_clear()

    client = TestClient(create_app())
    body = client.get("/api/meta").json()

    assert body["provider"]["name"] == "ollama"
    # The local 3B model is text-only; image and speech must degrade, not appear.
    assert body["provider"]["capabilities"] == ["text"]
    assert "not legal advice" in body["disclaimer"]

    get_settings.cache_clear()
    get_provider.cache_clear()


def test_meta_does_not_crash_when_groq_key_missing(monkeypatch):
    """Misconfiguration should surface in the response, not prevent boot."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from app.config import get_settings
    from app.llm.registry import get_provider

    get_settings.cache_clear()
    get_provider.cache_clear()

    client = TestClient(create_app())
    response = client.get("/api/meta")

    assert response.status_code == 200
    assert response.json()["provider"]["chat_model"] == "unconfigured"

    get_settings.cache_clear()
    get_provider.cache_clear()
