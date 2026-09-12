"""System route tests.

Configuration isolation is handled by conftest: the suite runs from a directory
with no .env, and settings caches are cleared around each test.
"""

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

    body = TestClient(create_app()).get("/api/meta").json()

    assert body["provider"]["name"] == "ollama"
    # The local 3B model is text-only; image and speech must degrade, not appear.
    assert body["provider"]["capabilities"] == ["text"]
    assert "not legal advice" in body["disclaimer"]


def test_meta_does_not_crash_when_groq_key_missing(monkeypatch):
    """Misconfiguration should surface in the response, not prevent boot."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    response = TestClient(create_app()).get("/api/meta")

    assert response.status_code == 200
    assert response.json()["provider"]["chat_model"] == "unconfigured"


def test_groq_declares_only_capabilities_backed_by_a_configured_model(monkeypatch):
    """A capability asserted but unbacked by a model fails at call time, which is
    the failure the declaration exists to prevent. No vision model is offered on
    the current catalogue, so vision must not be advertised."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_not_a_real_key")

    body = TestClient(create_app()).get("/api/meta").json()

    assert body["provider"]["capabilities"] == ["text", "transcription"]


def test_vision_is_declared_when_a_vision_model_is_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_not_a_real_key")
    monkeypatch.setenv("GROQ_VISION_MODEL", "some/vision-model")

    body = TestClient(create_app()).get("/api/meta").json()

    assert "vision" in body["provider"]["capabilities"]


def test_meta_lists_which_models_can_actually_answer():
    client = TestClient(create_app())
    """The interface reads this instead of assuming a local model exists."""
    body = client.get("/api/meta").json()

    names = {p["name"] for p in body["providers"]}
    assert names == {"groq", "ollama"}
    for choice in body["providers"]:
        # An unavailable model says why, so the interface can show a reason
        # rather than a disabled control with no explanation.
        assert choice["available"] or choice["note"]


def test_asking_an_unavailable_model_is_refused_with_the_reason(monkeypatch):
    client = TestClient(create_app())
    from app.api import routes

    monkeypatch.setattr(routes, "local_provider_reachable", lambda: False)
    response = client.post(
        "/api/ask",
        json={"question": "Is theft a bailable offence?", "provider": "ollama"},
    )

    assert response.status_code == 503
    assert "no Ollama server is reachable" in response.json()["detail"]


def test_a_deployment_can_say_why_its_local_model_is_not_answering(monkeypatch):
    """A Space fetches 3.3 GB on every cold start, and for the first minutes of
    one the local model is absent rather than missing. "No Ollama server is
    reachable" is true throughout that and tells a visitor nothing: they cannot
    start one, and nobody has told them one is coming."""
    from app.api import routes
    from app import services

    monkeypatch.setattr(routes, "local_provider_reachable", lambda: False)
    monkeypatch.setattr(services, "_describe_local", lambda: "still arriving — 41%")

    client = TestClient(create_app())
    body = client.get("/api/meta").json()
    local = next(p for p in body["providers"] if p["name"] == "ollama")

    assert local["available"] is False
    assert local["note"] == "still arriving — 41%"


def test_without_one_the_plain_fact_is_reported(monkeypatch):
    from app.api import routes
    from app import services

    monkeypatch.setattr(routes, "local_provider_reachable", lambda: False)
    monkeypatch.setattr(services, "_describe_local", None)

    client = TestClient(create_app())
    body = client.get("/api/meta").json()
    local = next(p for p in body["providers"] if p["name"] == "ollama")

    assert "no Ollama server is reachable" in local["note"]


def test_asking_an_unknown_model_is_a_422():
    client = TestClient(create_app())
    response = client.post(
        "/api/ask",
        json={"question": "Is theft a bailable offence?", "provider": "nope"},
    )

    assert response.status_code == 422


def test_the_answer_cache_distinguishes_models():
    """Regression class. Two models answering one question are two answers.

    The key carries the model name, so switching providers cannot serve what the
    other one said — the same defect that made the evaluation cache serve an old
    prompt's answers as a new prompt's.
    """
    from app.api.limits import AnswerCache

    question = "Is theft a bailable offence?"
    hosted = AnswerCache.key(question, model="openai/gpt-oss-120b", index="i")
    local = AnswerCache.key(question, model="qwen2.5:3b-instruct", index="i")

    assert hosted != local


def test_speech_survives_choosing_the_text_only_model(monkeypatch):
    """Regression, visible in the interface.

    Selecting the local model made the Speak button vanish, because /api/meta
    reported the answering model's capabilities as the whole deployment's. ADR
    0004 erases modality at this boundary: what hears the question and what
    answers it are different jobs, and the hosted provider transcribes either
    way.
    """
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-for-capability-reporting")

    body = TestClient(create_app()).get("/api/meta").json()

    assert body["provider"]["name"] == "ollama"
    # The answering model is text-only...
    assert "transcription" not in body["provider"]["capabilities"]
    # ...and speech is still offered, because something else can hear.
    assert "speech" in body["features"]


def test_speech_is_absent_when_nothing_can_transcribe(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    body = TestClient(create_app()).get("/api/meta").json()

    assert "speech" not in body["features"]
