"""Re-scoring a recorded run.

A score is derived from an answer. When the scorer is corrected, the runs recorded
under the old one are reporting numbers nobody would defend, and re-running is the
wrong remedy: it spends a hosted budget to re-measure text that has not changed, and
it moves the prompt and the corpus at the same time, so nothing is attributable.
"""

from __future__ import annotations

import json

import pytest

from app.evaluation import rescore as rescore_module


@pytest.fixture
def run_dir(tmp_path):
    run = tmp_path / "stage-9"
    run.mkdir()
    (run / "summary.json").write_text(
        json.dumps(
            {
                "stage": 9,
                "system": "rag-legal-chunks",
                "provider": "groq",
                "model": "test-model",
                "excerpt_validity": 0.5,
                "questions": 2,
            }
        ),
        encoding="utf-8",
    )
    return run


def test_a_run_without_stored_answers_refuses_rather_than_guessing(run_dir, capsys):
    code = rescore_module.rescore(run_dir)
    out = capsys.readouterr().out

    assert code == 2
    assert "cannot be re-scored" in out
    # The old summary is left exactly as it was.
    assert json.loads((run_dir / "summary.json").read_text())["excerpt_validity"] == 0.5


def test_a_dry_run_writes_nothing(run_dir, monkeypatch, capsys):
    (run_dir / "answers.jsonl").write_text(
        json.dumps(
            {
                "question_id": "q-0001",
                "text": "...",
                "citations": [],
                "refused": True,
                "model": "test-model",
                "raw": "",
                "error": None,
                "retrieved_sections": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = (run_dir / "summary.json").read_text()

    code = rescore_module.rescore(run_dir, dry_run=True)

    assert code == 0
    assert (run_dir / "summary.json").read_text() == before


def test_a_rescored_summary_says_which_scorer_produced_it(run_dir):
    """Two rows in one table must be distinguishable, or the table is a mixture."""
    (run_dir / "answers.jsonl").write_text(
        json.dumps(
            {
                "question_id": "q-0001",
                "text": "...",
                "citations": [],
                "refused": True,
                "model": "test-model",
                "raw": "",
                "error": None,
                "retrieved_sections": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert rescore_module.rescore(run_dir) == 0

    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["rescored_with"] == rescore_module.SCORER_VERSION
    # One answer, against a gold set with many more questions in it.
    assert summary["missing_answers"] == summary["dataset_questions"] - 1
    assert summary["provider"] == "groq"
