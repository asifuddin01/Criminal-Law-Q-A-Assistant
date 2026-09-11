"""Speech input.

The endpoint returns text rather than answering it. A mis-transcription would
otherwise become a retrieval failure with no visible cause — the user asked one thing
and the system answered another, with nothing in the reply revealing the swap.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.llm.base import Capability, Completion, LLMProvider
from app.main import create_app


class StubProvider(LLMProvider):
    name = "stub"

    def __init__(self, *, transcription: bool = True, text: str = "heard this") -> None:
        self._transcription = transcription
        self._text = text
        self._transcription_model = "whisper-stub"
        self.calls: list[tuple[str, str | None]] = []

    @property
    def capabilities(self):
        caps = {Capability.TEXT}
        if self._transcription:
            caps.add(Capability.TRANSCRIPTION)
        return frozenset(caps)

    async def complete(self, messages, *, temperature=None, max_tokens=None):
        return Completion(text="", model="stub")

    async def transcribe(self, audio, filename, *, language=None):
        self.calls.append((filename, language))
        return self._text


@pytest.fixture
def client():
    return TestClient(create_app())


def _post(client, *, content=b"fake audio", content_type="audio/webm", **data):
    return client.post(
        "/api/transcribe",
        files={"audio": ("clip.webm", content, content_type)},
        data=data,
    )


def test_speech_returns_the_text_rather_than_an_answer(client, monkeypatch):
    provider = StubProvider(text="পুলিশ কখন গ্রেপ্তার করতে পারে?")
    monkeypatch.setattr(routes, "get_provider", lambda: provider)

    response = _post(client, language="bn")

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "পুলিশ কখন গ্রেপ্তার করতে পারে?"
    assert body["language"] == "bn"
    assert body["seconds"] >= 0


def test_a_provider_without_transcription_says_so_rather_than_failing(
    client, monkeypatch
):
    """The capability is declared, not assumed. A deployment on the local model has
    no transcription, and should say that instead of erroring at call time."""
    monkeypatch.setattr(
        routes, "get_provider", lambda: StubProvider(transcription=False)
    )

    response = _post(client)

    assert response.status_code == 503
    assert "transcription" in response.json()["detail"].lower()


def test_empty_audio_is_rejected(client, monkeypatch):
    monkeypatch.setattr(routes, "get_provider", lambda: StubProvider())

    response = _post(client, content=b"")

    assert response.status_code == 422


def test_oversized_audio_is_rejected_before_the_provider(client, monkeypatch):
    """Rejected locally so a long upload is not spent before the provider refuses
    it."""
    provider = StubProvider()
    monkeypatch.setattr(routes, "get_provider", lambda: provider)

    response = _post(client, content=b"x" * (routes.MAX_AUDIO_BYTES + 1))

    assert response.status_code == 413
    assert provider.calls == []


def test_silence_is_reported_rather_than_returned_as_an_empty_question(
    client, monkeypatch
):
    monkeypatch.setattr(routes, "get_provider", lambda: StubProvider(text="   "))

    response = _post(client)

    assert response.status_code == 422
    assert "recognised" in response.json()["detail"]


@pytest.mark.parametrize(
    ("content_type", "expected_suffix"),
    [
        ("audio/webm", "webm"),
        ("audio/mp4", "m4a"),
        ("audio/wav", "wav"),
        ("application/octet-stream", "webm"),
    ],
)
def test_the_filename_carries_a_format_the_model_can_read(
    client, monkeypatch, content_type, expected_suffix
):
    """Whisper infers the format from the filename, and a browser recording arrives
    as a blob with no useful name."""
    provider = StubProvider()
    monkeypatch.setattr(routes, "get_provider", lambda: provider)

    _post(client, content_type=content_type)

    assert provider.calls[0][0] == f"question.{expected_suffix}"
