"""Report artefacts.

A chart is read by people who will not open the summaries behind it, so its
caption is taken on trust. This file exists because the caption has twice said
something the axis underneath it contradicted.
"""

from __future__ import annotations

from app.evaluation.report import _dataset_note


def _run(stage: int, measured: int, dataset: int = 101) -> dict:
    return {
        "stage": stage,
        "measured": measured,
        "questions": measured,
        "dataset_questions": dataset,
        "errors": 0,
    }


def test_one_set_fully_measured_says_so():
    note = _dataset_note([_run(1, 101), _run(2, 101), _run(3, 101)])
    assert note == "same 101 questions throughout, all measured"


def test_a_set_the_stages_cover_unequally_does_not_claim_they_are_equal():
    """Regression, and the reason this file exists.

    The hosted track's stages 1 and 2 were recorded before the gold set grew, so
    they cover 93 and 95 of 101 while stages 3 and 4 cover all of it. Every run
    records the same `dataset_questions`, so a check on that alone concluded "the
    same 101 questions at every stage" — printed directly above labels reading
    93/93 and 95/95.
    """
    note = _dataset_note([_run(1, 93), _run(2, 95), _run(3, 101), _run(4, 101)])
    assert "the same 101 questions at every stage" not in note
    assert "101" in note and "see the labels below" in note


def test_differing_gold_sets_defer_to_the_labels():
    note = _dataset_note([_run(1, 93, dataset=95), _run(2, 101, dataset=101)])
    assert note == "question counts differ between stages — see the labels below"
