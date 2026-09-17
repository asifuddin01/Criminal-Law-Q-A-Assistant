"""What a reader is shown when there is no answer.

Refusal is a first-class outcome here, which makes its text part of the answer:
it is where the system says what is missing or asks what was meant. Two defects
lived in this path. The model's own reason was replaced with a fixed phrase, and
a refusal by the citation gate returned the very text it had refused.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import routes
from app.main import create_app
from app.qa.schema import Answer, Citation
from app.qa.validation import validate


class _FixedAnswer:
    """A QA system that returns one prepared answer, so the route is tested alone."""

    model_name = "fixed-model"
    index_name = "fixed-index"
    fingerprint = "fixed"

    def __init__(self, answer: Answer) -> None:
        self._answer = answer

    async def answer(self, question, *, extra_chunks=None) -> Answer:
        return self._answer


def _ask(monkeypatch, answer: Answer, question: str) -> dict:
    monkeypatch.setattr(routes, "get_qa", lambda chosen=None: _FixedAnswer(answer))
    monkeypatch.setattr(routes, "get_corpora", lambda: {})
    monkeypatch.setattr(routes, "get_schedule", lambda: [])
    response = TestClient(create_app()).post("/api/ask", json={"question": question})
    assert response.status_code == 200, response.text
    return response.json()


def test_when_the_model_declines_its_own_reason_is_kept():
    ask_back = "Which offence are you asking about? Whether bail is available depends on it."
    result = validate(Answer(text=ask_back, refused=True), {})

    assert result.refused
    assert result.reason == ask_back


def test_a_decline_with_no_words_still_says_so():
    result = validate(Answer(text="   ", refused=True), {})
    assert result.reason == "the model declined to answer"


def test_the_reader_sees_the_question_the_model_asked(monkeypatch):
    """Regression. Both interfaces show `reason` for a refusal, and it used to be
    a fixed phrase — so a clarifying question never reached the screen."""
    ask_back = "Which offence are you asking about? Bail depends on the offence."
    body = _ask(monkeypatch, Answer(text=ask_back, refused=True), "Will I get bail?")

    assert body["refused"] is True
    assert body["reason"] == ask_back
    assert body["answer"] == ask_back


def test_a_withheld_answer_does_not_carry_the_text_that_was_withheld(monkeypatch):
    """Regression. The gate refuses an answer nothing substantiates, and the API
    returned that answer anyway in `answer` — invisible in the interfaces, which
    show `reason`, and delivered to any other caller."""
    invented = "Police may hold anyone for ninety days without charge."
    body = _ask(
        monkeypatch,
        Answer(
            text=invented,
            citations=[
                Citation(section="9999", source="CrPC", quote="hold anyone for ninety days")
            ],
            retrieved_sections=["CrPC:9999"],
        ),
        "How long can the police hold someone?",
    )

    assert body["refused"] is True
    assert invented not in body["answer"]
    assert "withheld" in body["reason"].lower()
    assert body["citations"] == []
