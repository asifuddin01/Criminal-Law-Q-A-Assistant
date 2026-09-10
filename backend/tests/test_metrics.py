"""Scoring tests.

The metrics are the instrument. A bug here does not produce a visible failure — it
produces a number that is wrong in a direction nobody checks.
"""

from __future__ import annotations

from app.evaluation.metrics import QuestionScore, aggregate


def _score(**kwargs) -> QuestionScore:
    base = dict(
        question_id="q-0001", slice="direct_lookup", answerable=True, refused=False
    )
    return QuestionScore(**{**base, **kwargs})


def test_errored_question_is_not_scored_as_a_correct_decision():
    """Regression. An errored answer has refused=False, so on an answerable
    question `refused != answerable` is true and 40 rate-limit failures were
    scored as correct refusal decisions, inflating refusal accuracy to 83%."""
    errored = _score(error="groq: Error code: 429")

    assert errored.measured is False
    assert errored.decided_correctly is False


def test_errors_are_excluded_from_rates_not_folded_into_them():
    scores = [
        _score(question_id="q-1", refused=False),  # answerable, answered: correct
        _score(question_id="q-2", error="429"),  # no measurement
        _score(question_id="q-3", error="429"),  # no measurement
    ]

    summary = aggregate(scores)

    assert summary["questions"] == 3
    assert summary["measured"] == 1
    assert summary["errors"] == 2
    # One measured question, decided correctly: 100%, not 33% and not 100% of three.
    assert summary["refusal_accuracy"] == 1.0


def test_refusal_is_correct_only_when_the_question_is_unanswerable():
    assert _score(answerable=False, refused=True).decided_correctly is True
    assert _score(answerable=False, refused=False).decided_correctly is False
    assert _score(answerable=True, refused=True).decided_correctly is False
    assert _score(answerable=True, refused=False).decided_correctly is True


def test_slice_breakdown_reports_errors_separately():
    scores = [
        _score(question_id="q-1", slice="direct_lookup"),
        _score(question_id="q-2", slice="direct_lookup", error="429"),
    ]

    bucket = aggregate(scores)["by_slice"]["direct_lookup"]

    assert bucket["n"] == 2
    assert bucket["errors"] == 1
    assert bucket["measured"] == 1
    assert bucket["refusal_accuracy"] == 1.0


def test_citation_existence_and_precision_are_independent():
    """The baseline cites real sections that are the wrong ones, so existence can
    be perfect while precision is zero. Both metrics are needed."""
    scores = [_score(citations_made=4, citations_existing=4, citations_correct=0)]

    summary = aggregate(scores)

    assert summary["citation_existence"] == 1.0
    assert summary["hallucinated_citation_rate"] == 0.0
    assert summary["citation_precision"] == 0.0


def test_rates_are_none_rather_than_zero_when_nothing_was_measured():
    summary = aggregate([_score(error="429")])

    assert summary["citation_existence"] is None
    assert summary["refusal_accuracy"] is None
