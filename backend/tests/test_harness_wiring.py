"""Harness CLI wiring.

Every flag here is tested for being *consulted*, not merely accepted.

This file exists because of a real bug: a patch added `--wait-for-budget` to the
argument parser but failed to apply the change that reads it, because the
surrounding code had moved. The flag appeared in `--help`, argparse accepted it
without complaint, lint passed — and an overnight run stopped on the first daily
limit instead of waiting through it. Nothing short of running it, or a test like
this, would have caught it.
"""

from __future__ import annotations

import inspect

import pytest

from app.evaluation import harness


def _captured(monkeypatch) -> dict:
    seen: dict = {}

    async def fake_run_stage(stage, **kwargs):
        seen["stage"] = stage
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(harness, "run_stage", fake_run_stage)
    return seen


@pytest.mark.parametrize(
    ("argv", "key", "expected"),
    [
        (["--wait-for-budget"], "wait_for_budget", True),
        ([], "wait_for_budget", False),
        (["--provider", "ollama"], "provider_name", "ollama"),
        (["--no-cache"], "use_cache", False),
        ([], "use_cache", True),
        (["--concurrency", "5"], "concurrency", 5),
        (["--limit", "7"], "limit", 7),
    ],
)
def test_each_flag_reaches_run_stage(monkeypatch, argv, key, expected):
    seen = _captured(monkeypatch)

    harness.main(argv)

    assert seen[key] == expected


def test_run_stage_accepts_every_argument_main_passes(monkeypatch):
    """A flag main passes that run_stage does not accept is a TypeError at the
    worst possible moment — after a long sweep has already spent its budget."""
    # Capture the real signature before the stub replaces it.
    accepted = set(inspect.signature(harness.run_stage).parameters)

    seen = _captured(monkeypatch)
    harness.main(["--wait-for-budget", "--provider", "ollama", "--no-cache"])

    assert set(seen) - {"stage"} <= accepted


def test_run_stage_reads_the_flag_rather_than_only_accepting_it():
    """The exact bug: the parameter existed in the signature while the body never
    consulted it."""
    source = inspect.getsource(harness.run_stage)

    assert "wait_for_budget" in source.split(") -> int:", 1)[1]


def test_the_cache_key_changes_when_the_prompt_changes():
    """A cache keyed only on the question would serve answers produced by an earlier
    prompt as though they came from the new one, so a prompt change would appear to
    have no effect and the experiment would silently re-measure the old prompt."""
    same = harness._cache_key("sys", "model", "question", "fingerprint-a")
    other = harness._cache_key("sys", "model", "question", "fingerprint-b")

    assert same != other


def test_both_answering_systems_expose_a_prompt_fingerprint():
    from app.qa.baseline import BaselineLLM
    from app.qa.rag import RetrievalQA

    for system in (BaselineLLM, RetrievalQA):
        assert isinstance(system.fingerprint, property)


def test_the_fingerprint_changes_when_the_corpus_changes():
    """Regression. The harness keyed answers on the prompt and nothing else.

    `index_name` carried a docstring saying it was part of the cache key. It was —
    in the API, which assembles its own key — while the evaluation harness keyed on
    the prompt alone. Nothing collided, because each stage has a distinct name. But
    rebuilding an index in place is precisely what the incremental update path
    exists to do, and every answer would then have been served from the corpus as
    it stood before the update, attributed to text the system no longer held.
    """
    import numpy as np

    from app.qa.rag import RetrievalQA
    from app.retrieval import VectorIndex
    from app.retrieval.chunking import Chunk

    def index(text: str) -> VectorIndex:
        chunk = Chunk(
            chunk_id="legal-CrPC-54-0",
            text=text,
            section_number="54",
            marginal_note="When police may arrest without warrant",
            part=None,
            chapter=None,
            strategy="legal_aware",
        )
        return VectorIndex([chunk], np.zeros((1, 4), dtype="float32"), "test-model")

    before = index("54. (1) Any police-officer may arrest without warrant.")
    after = index("54. (1) Any police-officer may arrest without an order.")

    assert before.content_fingerprint != after.content_fingerprint

    system = RetrievalQA(object(), before, name="rag-legal-chunks")
    updated = RetrievalQA(object(), after, name="rag-legal-chunks")

    assert system.fingerprint != updated.fingerprint


def test_the_fingerprint_changes_when_k_changes():
    """How many chunks are retrieved changes what the model was shown."""
    import numpy as np

    from app.qa.rag import RetrievalQA
    from app.retrieval import VectorIndex
    from app.retrieval.chunking import Chunk

    chunk = Chunk(
        chunk_id="legal-CrPC-54-0",
        text="54. (1) Any police-officer may arrest without warrant.",
        section_number="54",
        marginal_note="",
        part=None,
        chapter=None,
        strategy="legal_aware",
    )
    idx = VectorIndex([chunk], np.zeros((1, 4), dtype="float32"), "test-model")

    assert (
        RetrievalQA(object(), idx, name="s", k=8).fingerprint
        != RetrievalQA(object(), idx, name="s", k=6).fingerprint
    )
