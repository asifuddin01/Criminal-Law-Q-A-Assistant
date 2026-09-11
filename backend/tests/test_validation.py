"""Citation gate tests.

This is the last thing between a generated answer and a user, and the only
component that can refuse to emit an ungrounded one. Its failure mode is silent, so
each rule is tested in both directions.
"""

from __future__ import annotations

import pathlib

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
        _answer([Citation(section="61", quote=quote)], retrieved_sections=["CrPC:61"]),
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
            retrieved_sections=["CrPC:61"],
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
        _answer([Citation(section="9999")], retrieved_sections=["CrPC:9999"]), corpus
    )

    assert result.refused is True
    assert any("no section 9999" in d["reason"] for d in result.dropped)


@corpus_only
def test_a_real_section_never_retrieved_is_dropped(corpus):
    """The stage 1 failure mode: citing a real section of the wrong statute from
    memory. Real, resolvable, and not grounded in anything retrieved."""
    result = validate(
        _answer([Citation(section="57")], retrieved_sections=["CrPC:61", "CrPC:167"]), corpus
    )

    assert result.refused is True
    assert any("retrieved context" in d["reason"] for d in result.dropped)


@corpus_only
def test_an_answer_with_nothing_substantiated_becomes_a_refusal(corpus):
    result = validate(_answer([], retrieved_sections=["CrPC:61"]), corpus)

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
        _answer([Citation(section="61", quote="the")], retrieved_sections=["CrPC:61"]),
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
        _answer([Citation(section="61", quote=reflowed)], retrieved_sections=["CrPC:61"]),
        corpus,
    )

    assert result.citations[0].quote_verified is True


# --- Schedule II citations ---------------------------------------------------------


@pytest.fixture(scope="module")
def schedule():
    from app.ingest import parse_schedule, schedule_path

    return parse_schedule(schedule_path()) if schedule_path().exists() else []


schedule_only = pytest.mark.skipif(
    not (pathlib.Path(__file__).resolve().parents[2] / "data" / "raw"
         / "crpc-schedule-ii.pdf").exists(),
    reason="Schedule II not fetched; run: python -m app.ingest --schedule",
)


@corpus_only
@schedule_only
def test_a_schedule_citation_resolves_against_schedule_ii(corpus, schedule):
    result = validate(
        Answer(
            text="Theft is not bailable.",
            citations=[Citation(section="379", source="Schedule II")],
            retrieved_sections=["ScheduleII:379"],
        ),
        corpus,
        schedule=schedule,
    )

    assert result.grounded
    assert result.citations[0].source == "ScheduleII"
    assert "theft" in result.citations[0].marginal_note.lower()


@corpus_only
@schedule_only
def test_a_penal_code_number_is_not_validated_against_the_crpc(corpus, schedule):
    """The reason citations carry a source at all. Penal Code section 379 is theft;
    CrPC section 379 is about appeals. A citation claiming Schedule II must be
    checked against Schedule II, and one claiming the CrPC against the CrPC —
    resolving either against the other would confirm a wrong citation."""
    result = validate(
        Answer(
            text="...",
            citations=[Citation(section="9999", source="Schedule II")],
            retrieved_sections=["ScheduleII:9999"],
        ),
        corpus,
        schedule=schedule,
    )

    assert result.refused
    assert any("Schedule II" in d["reason"] for d in result.dropped)


@corpus_only
@schedule_only
def test_a_schedule_row_never_retrieved_is_dropped(corpus, schedule):
    result = validate(
        Answer(
            text="...",
            citations=[Citation(section="302", source="Schedule II")],
            retrieved_sections=["ScheduleII:379"],
        ),
        corpus,
        schedule=schedule,
    )

    assert result.refused
    assert any("retrieved context" in d["reason"] for d in result.dropped)


def test_a_verified_citation_carries_how_the_section_was_amended():
    """Current wording is not the whole answer to a legal question.

    A provision substituted with effect from a date after the events a user is
    asking about is the wrong provision for those events, and nothing in the text
    says so. The parser has carried these records since ingestion; nothing showed
    them.
    """
    from datetime import date

    from app.ingest.models import Act, Amendment, Operation, Section, SectionUnit
    from app.qa.schema import CRPC, Answer, Citation
    from app.qa.validation import validate

    act = Act(
        act_id=75,
        title="The Code of Criminal Procedure, 1898",
        source_url="x",
        fetched_at="2026-01-01T00:00:00Z",
        source_hash="0" * 64,
        sections=[
            Section(
                number="54",
                units=[
                    SectionUnit(
                        marginal_note="When police may arrest without warrant",
                        text="54. (1) Any police-officer may arrest without warrant.",
                        footnote_markers=[74, 9],
                    )
                ],
            )
        ],
        amendments={
            74: Amendment(
                marker=74,
                operation=Operation.SUBSTITUTED,
                text="Section 54 was substituted in 2026.",
                amending_act_id=1640,
                act_number="XI of 2026",
                effective_from=date(2025, 8, 10),
            ),
            9: Amendment(
                marker=9,
                operation=Operation.INSERTED,
                text="An older change with no stated date.",
            ),
        },
    )
    answer = Answer(
        text="A police officer may arrest without warrant.",
        citations=[
            Citation(
                section="54",
                source=CRPC,
                quote="Any police-officer may arrest without warrant.",
            )
        ],
        retrieved_sections=["CrPC:54"],
    )

    result = validate(answer, {CRPC: act})
    citation = result.citations[0]

    assert citation.quote_verified
    assert [a.operation for a in citation.amendments] == ["substituted", "inserted"]
    assert citation.amendments[0].effective_from == "2025-08-10"
    assert citation.amendments[0].act_number == "XI of 2026"
    assert "act-details-1640" in citation.amendments[0].source_url
    # The undated record is kept and sorted last, not dropped: the footnote still
    # says what changed, and discarding it would hide an amendment because its date
    # failed to parse.
    assert citation.amendments[1].effective_from is None
