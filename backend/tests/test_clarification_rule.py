"""The clarification rule, and the evidence it is applied on.

The rule was tested for every model and failed its criteria on the local one, so it
is applied per provider. These tests hold the parts that make that safe: the
shipped prompt is untouched unless a provider is chosen, the measured prompt is the
one applied, and the rule's example is not taken from the test set.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from types import SimpleNamespace

from app.qa import rag
from app.qa.rag import (
    CLARIFICATION_RULE,
    CLARIFYING_PROMPT,
    SYSTEM_PROMPT,
    VAGUE_QUESTION_RULE,
    RetrievalQA,
)

GOLD = pathlib.Path(__file__).resolve().parents[2] / "eval" / "dataset" / "gold.jsonl"


def _system(clarify: bool) -> RetrievalQA:
    index = SimpleNamespace(model_name="m", content_fingerprint="c")
    provider = SimpleNamespace(name="p", _chat_model="p-model")
    return RetrievalQA(provider, index, name="stage", clarify=clarify)


def test_the_shipped_prompt_is_the_default():
    assert VAGUE_QUESTION_RULE in SYSTEM_PROMPT
    assert _system(clarify=False)._system_prompt == SYSTEM_PROMPT


def test_the_rule_replaces_the_old_one_rather_than_contradicting_it():
    assert CLARIFICATION_RULE in CLARIFYING_PROMPT
    assert VAGUE_QUESTION_RULE not in CLARIFYING_PROMPT


def test_the_applied_prompt_is_byte_for_byte_the_one_measured():
    """If this fails, the rule has been edited since it was measured, and the
    experiment's results no longer describe the prompt in use."""
    digest = hashlib.sha256(CLARIFYING_PROMPT.encode("utf-8")).hexdigest()
    assert digest[:16] == "cb571e45d1645b73"


def test_the_rule_changes_the_cache_fingerprint():
    """Answers produced under one prompt must never be served for the other."""
    assert _system(clarify=True).fingerprint != _system(clarify=False).fingerprint


def test_a_provider_gets_the_rule_only_if_it_is_listed(monkeypatch):
    monkeypatch.setattr(rag, "CLARIFYING_PROVIDERS", frozenset({"groq"}))
    assert rag.clarifies("groq") is True
    assert rag.clarifies("ollama") is False


def test_the_rule_ships_for_the_hosted_model_and_not_the_local_one():
    """Each side of this is a measured result, not a preference.

    Hosted: passed its pre-registered criteria on all 101 questions. Local: failed
    the same criteria, declining questions the extracts plainly answer. Adding the
    local model here would ship a change that was measured to make it worse.
    """
    assert rag.clarifies("groq") is True
    assert rag.clarifies("ollama") is False


def test_the_rules_example_is_not_a_question_it_is_scored_on():
    """An example lifted from the dataset would teach the prompt its own test."""
    lines = GOLD.read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line)["question"].lower() for line in lines if line.strip()]
    assert not any("will the police charge me" in q for q in questions)
