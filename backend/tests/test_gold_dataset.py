"""Gold dataset tests.

The dataset is the measuring instrument for every later stage, so it is tested like
one — including negative tests that confirm the validator actually rejects bad
labels, rather than passing because it checks nothing.
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.evaluation import (
    SECTION_EXPECTATIONS,
    Slice,
    load_gold,
    validate_against_corpus,
)
from app.ingest import cache_path, parse_act

CORPUS = cache_path(75)
corpus_only = pytest.mark.skipif(
    not CORPUS.exists(), reason="corpus not fetched; run: python -m app.ingest"
)


@pytest.fixture(scope="module")
def gold():
    return load_gold()


@pytest.fixture(scope="module")
def corpora():
    if not CORPUS.exists():
        return {}
    return {
        "CrPC": parse_act(
            CORPUS.read_text(encoding="utf-8", errors="replace"),
            act_id=75,
            source_url="https://bdlaws.minlaw.gov.bd/act-print-75.html",
        )
    }


def test_dataset_loads_and_ids_are_unique(gold):
    assert len(gold) == 95
    assert len({q.id for q in gold}) == len(gold)


def test_every_slice_is_populated(gold):
    counts = Counter(q.slice for q in gold)
    for slice_ in Slice:
        assert counts[slice_] > 0, f"slice {slice_.value} is empty"


def test_unanswerable_and_ambiguous_slices_are_substantial(gold):
    """A dataset weighted only toward answerable questions teaches a system to
    always answer, which is the failure the brief asks us to avoid."""
    refusing = sum(1 for q in gold if not q.answerable)
    assert refusing / len(gold) > 0.2


def test_answerable_questions_carry_labels_and_others_do_not(gold):
    for question in gold:
        if question.answerable:
            assert question.gold_sections, f"{question.id} answerable with no label"
        else:
            assert not question.gold_sections, f"{question.id} unanswerable with label"


def test_bangla_slice_is_actually_bangla(gold):
    bangla = [q for q in gold if q.slice is Slice.BANGLA]
    assert bangla
    for question in bangla:
        assert question.language == "bn"
        # Bengali block starts at U+0980.
        assert any("ঀ" <= ch <= "৿" for ch in question.question)


def test_unanswerable_questions_record_what_would_answer_them(gold):
    """Unanswerability is relative to the current corpus. Recording the act that
    would answer a question keeps these labels correct as the corpus grows."""
    schedule_dependent = [
        q for q in gold if "CrPC-Schedule-II" in q.requires_acts
    ]
    assert schedule_dependent, "offence-classification questions must be represented"
    for question in schedule_dependent:
        assert not question.answerable


@corpus_only
def test_every_gold_label_resolves_against_the_corpus(gold, corpora):
    issues = validate_against_corpus(gold, corpora)
    assert not issues, "\n".join(f"{i.question_id}: {i.problem}" for i in issues)


@corpus_only
def test_validator_rejects_a_label_that_does_not_exist(gold, corpora):
    """Negative test: confirm the validator fails on a bad label rather than
    passing because it checks nothing."""
    broken = [q.model_copy(update={"gold_sections": ["CrPC-9999"]}) for q in gold[:1]]
    issues = validate_against_corpus(broken, corpora)
    assert any("does not exist" in i.problem for i in issues)


@corpus_only
def test_validator_rejects_a_label_pointing_at_the_wrong_provision(
    gold, corpora, monkeypatch
):
    """The content expectation is what catches a label that resolves but is wrong."""
    monkeypatch.setitem(
        SECTION_EXPECTATIONS, "CrPC-54", "this phrase is not in section 54"
    )
    subject = [q for q in gold if "CrPC-54" in q.gold_sections][:1]
    assert subject
    issues = validate_against_corpus(subject, corpora)
    assert any("wrong provision" in i.problem for i in issues)


@corpus_only
def test_content_expectations_cover_the_frequently_cited_sections(gold, corpora):
    cited = Counter(s for q in gold for s in q.gold_sections)
    uncovered = [s for s, _ in cited.most_common() if s not in SECTION_EXPECTATIONS]
    assert not uncovered, f"cited sections without a content expectation: {uncovered}"
