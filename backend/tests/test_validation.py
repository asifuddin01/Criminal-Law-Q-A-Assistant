"""Citation gate tests.

This is the last thing between a generated answer and a user, and the only
component that can refuse to emit an ungrounded one. Its failure mode is silent, so
each rule is tested in both directions.
"""

from __future__ import annotations

import pytest

from app.ingest import cache_path, parse_act
from app.qa.schema import Answer, Citation
from app.qa.validation import validate

CORPUS = cache_path(75)
corpus_only = pytest.mark.skipif(
    not CORPUS.exists(), reason="corpus not fetched; run: python -m app.ingest"
)


@pytest.fixture(scope="module")
def corpus():
    if not CORPUS.exists():
        return None
    return parse_act(
        CORPUS.read_text(encoding="utf-8", errors="replace"),
        act_id=75,
        source_url="https://bdlaws.minlaw.gov.bd/act-print-75.html",
    )


def _answer(citations, **kwargs) -> Answer:
    return Answer(text="an answer", citations=citations, **kwargs)


@corpus_only
def test_a_verbatim_quotation_passes_and_is_marked_verified(corpus):
    quote = corpus.section("61").text[40:140]
    result = validate(
        _answer([Citation(section="61", quote=quote)], retrieved_sections=["61"]),
        corpus,
    )

    assert result.grounded
    assert result.citations[0].quote_verified is True
    assert result.citations[0].section == "61"


@corpus_only
def test_a_fabricated_quotation_is_stripped_but_the_section_survives(corpus):
    """A fabricated quotation is worse than none, while the section reference may
    still be sound. Stage 1 fabricated all 143 quotations it produced."""
    result = validate(
        _answer(
            [
                Citation(
                    section="61",
                    quote="Every person arrested shall be produced within twelve hours.",
                )
            ],
            retrieved_sections=["61"],
        ),
        corpus,
    )

    assert result.grounded
    assert result.citations[0].quote == ""
    assert result.citations[0].quote_verified is False
    assert any("does not appear" in d["reason"] for d in result.dropped)


@corpus_only
def test_a_section_that_does_not_exist_is_dropped(corpus):
    result = validate(
        _answer([Citation(section="9999")], retrieved_sections=["9999"]), corpus
    )

    assert result.refused is True
    assert any("no such section" in d["reason"] for d in result.dropped)


@corpus_only
def test_a_real_section_never_retrieved_is_dropped(corpus):
    """The stage 1 failure mode: citing a real section of the wrong statute from
    memory. Real, resolvable, and not grounded in anything retrieved."""
    result = validate(
        _answer([Citation(section="57")], retrieved_sections=["61", "167"]), corpus
    )

    assert result.refused is True
    assert any("retrieved context" in d["reason"] for d in result.dropped)


@corpus_only
def test_an_answer_with_nothing_substantiated_becomes_a_refusal(corpus):
    result = validate(_answer([], retrieved_sections=["61"]), corpus)

    assert result.refused is True
    assert result.grounded is False
    assert "withheld" in result.reason


@corpus_only
def test_a_model_refusal_is_passed_through_untouched(corpus):
    result = validate(
        Answer(text="I cannot answer that", refused=True), corpus
    )

    assert result.refused is True
    assert result.citations == []


@corpus_only
def test_short_quotations_are_not_treated_as_evidence(corpus):
    """Below the minimum length a quotation matches too easily to prove anything,
    so it is neither verified nor counted against the answer."""
    result = validate(
        _answer([Citation(section="61", quote="the")], retrieved_sections=["61"]),
        corpus,
    )

    assert result.grounded
    assert result.citations[0].quote_verified is False
    assert not result.dropped


@corpus_only
def test_whitespace_differences_do_not_defeat_a_genuine_quotation(corpus):
    """Models reflow whitespace when copying. That is not fabrication."""
    original = corpus.section("61").text[40:160]
    reflowed = "\n   ".join(original.split(" ", 3))

    result = validate(
        _answer([Citation(section="61", quote=reflowed)], retrieved_sections=["61"]),
        corpus,
    )

    assert result.citations[0].quote_verified is True
