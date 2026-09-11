"""Parser tests.

Two layers. The fixture tests exercise the source conventions on a small handcrafted
document and run anywhere. The corpus tests run against the real cached act and are
skipped when it has not been fetched, since data/ is deliberately not committed.
"""

from __future__ import annotations

import pathlib
from datetime import date

import pytest

from app.ingest import DocumentRole, Operation, parse_act
from app.ingest.bdlaws import _clean

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_act.html"
CORPUS = pathlib.Path(__file__).parents[2] / "data" / "raw" / "act-print-75.html"


@pytest.fixture(scope="module")
def mini():
    return parse_act(
        FIXTURE.read_text(), act_id=999, source_url="https://example.invalid/mini"
    )


# --- source conventions, on the fixture -------------------------------------------


def test_act_metadata_is_read_from_the_document(mini):
    assert mini.title == "The Mini Test Act, 1900"
    assert mini.act_number == "IX OF 1900"
    assert mini.role is DocumentRole.OPERATIVE


def test_headings_nested_inside_a_row_apply_to_that_row(mini):
    """Part and chapter markup sits inside the row it opens, not before it. Read
    naively, the first section of every part is filed with no part at all."""
    section = mini.section("1")
    assert section.part == "Part I PRELIMINARY"
    assert section.chapter == "Chapter I"


def test_marginal_notes_are_whitespace_normalized(mini):
    assert mini.section("1").marginal_notes == ["Short title Commencement", "Extent"]


def test_units_without_a_number_continue_the_open_section(mini):
    section = mini.section("1")
    assert len(section.units) == 2
    assert "extends to the whole" in section.text


def test_leading_footnote_marker_is_not_read_as_a_section_number(mini):
    """A provision opening with an amended span begins with the footnote's digits.
    Extracting text before removing markers invents a section named after them."""
    assert [s.number for s in mini.sections] == ["1", "4", "6", "23", "24", "265-I"]
    # The marker is 7 and there is no section 7; an unstripped marker invents one.
    assert mini.section("1").footnote_markers == [7]


def test_whole_section_amendment_bracket_is_recorded_not_swallowed(mini):
    section = mini.section("6")
    assert section is not None, "bracketed section number must still be found"
    assert section.whole_section_amended is True
    assert section.is_repealed is False


def test_clause_level_repeal_does_not_repeal_the_section(mini):
    """Section 4 carries '(d) [Repealed ...]' partway through. An unanchored search
    marks the whole section repealed and deletes the Act's definitions."""
    section = mini.section("4")
    assert section.is_repealed is False
    assert '"judge" means a judge' in section.text


def test_paired_repeal_emits_both_sections(mini):
    for number in ("23", "24"):
        section = mini.section(number)
        assert section is not None, f"section {number} lost from a paired repeal"
        assert section.is_repealed is True


def test_hyphenated_section_number_is_its_own_section(mini):
    """265-I hyphenates where 265A does not. Missed, its text welds onto the
    preceding section and is then cited under the wrong number."""
    section = mini.section("265-I")
    assert section is not None
    assert "enter on his defence" in section.text


def test_footnote_marker_in_a_chapter_heading_is_stripped(mini):
    assert mini.section("6").chapter == "Chapter II OF COURTS"


# --- amendment apparatus -----------------------------------------------------------


def test_amendment_operation_and_provenance_are_parsed(mini):
    amendment = mini.amendments[2]
    assert amendment.operation is Operation.SUBSTITUTED
    assert amendment.amending_act_id == 1035
    assert amendment.act_number == "XXXII of 2009"
    assert amendment.effective_from == date(2007, 11, 1)


def test_amendment_without_an_effective_date_is_none_not_guessed(mini):
    assert mini.amendments[7].operation is Operation.OMITTED
    assert mini.amendments[7].effective_from is None
    assert mini.amendments[7].amending_act_id == 430


def test_amendments_resolve_from_the_section_that_carries_the_marker(mini):
    records = mini.amendments_for(mini.section("6"))
    assert [a.marker for a in records] == [2]


def test_content_hash_tracks_text_not_identity(mini):
    a, b = mini.section("1"), mini.section("4")
    assert a.content_hash != b.content_hash
    assert a.content_hash == mini.section("1").content_hash


# --- the real corpus ---------------------------------------------------------------

corpus_only = pytest.mark.skipif(
    not CORPUS.exists(),
    reason="corpus not fetched; run: python -m app.ingest",
)


@pytest.fixture(scope="module")
def crpc():
    return parse_act(
        CORPUS.read_text(encoding="utf-8", errors="replace"),
        act_id=75,
        source_url="https://bdlaws.minlaw.gov.bd/act-print-75.html",
    )


@corpus_only
def test_corpus_section_and_amendment_counts(crpc):
    """Counts from the 2026-09-10 snapshot. A change here means the published
    consolidation moved, which is a corpus event worth failing on."""
    assert len(crpc.sections) == 522
    assert len(crpc.amendments) == 599


@corpus_only
def test_corpus_section_numbers_are_unique_and_ordered(crpc):
    numbers = [s.number for s in crpc.sections]
    assert len(numbers) == len(set(numbers)), "duplicate section numbers"
    leading = [int("".join(c for c in n if c.isdigit())) for n in numbers]
    assert leading == sorted(leading), "sections out of document order"


@corpus_only
@pytest.mark.parametrize("number", ["1", "4", "54", "164", "265-I", "497", "561A", "565"])
def test_corpus_notable_sections_present(crpc, number):
    assert crpc.section(number) is not None


@corpus_only
def test_corpus_section_54_is_intact(crpc):
    """s.54 opens with an amendment marker, which is how it goes missing."""
    section = crpc.section("54")
    assert section.whole_section_amended is True
    assert "without warrant, arrest" in section.text
    assert section.chapter == "Chapter V OF ARREST, ESCAPE AND RETAKING"


@corpus_only
def test_corpus_definitions_section_survives_its_internal_repeals(crpc):
    section = crpc.section("4")
    assert section.is_repealed is False
    assert "bailable offence" in section.text
    assert "cognizable offence" in section.text


@corpus_only
def test_corpus_block_repealed_sections_are_genuinely_absent(crpc):
    """266-336 were replaced wholesale by the 265A-265L regime and do not appear in
    the consolidation. Their absence is the source's, not the parser's."""
    numbers = {s.number for s in crpc.sections}
    assert not any(str(n) in numbers for n in range(266, 337))
    assert "265L" in numbers and "337" in numbers


@corpus_only
def test_corpus_every_section_has_text_and_identity(crpc):
    for section in crpc.sections:
        assert section.number
        assert section.text.strip(), f"section {section.number} has no text"
        assert section.content_hash


@corpus_only
def test_corpus_amendment_markers_resolve(crpc):
    """Every marker cited in the text must exist in the footnote apparatus."""
    known = set(crpc.amendments)
    for section in crpc.sections:
        unknown = set(section.footnote_markers) - known
        assert not unknown, f"section {section.number} cites unknown footnotes {unknown}"


# --- footnote removal leaves no trace of itself ------------------------------


def test_footnote_removal_does_not_leave_a_gap_before_punctuation():
    """Regression. A marker sits between a word and the punctuation after it.

    "the Evidence Act, 1872 [7], section 24" becomes "1872 , section 24" once the
    marker goes. Twenty-seven of these reached the ingested Code. The gap is not in
    the statute, it is visible to anyone reading a quoted excerpt, and it made a
    faithful quotation of section 163 fail verification against its own section.
    """
    assert _clean("the Evidence Act, 1872 , section 24") == (
        "the Evidence Act, 1872, section 24"
    )
    assert _clean("Procedure, 1898 ; and it shall") == "Procedure, 1898; and it shall"
    assert _clean("headman , accountant") == "headman, accountant"


def test_a_subsection_whose_number_was_a_marker_does_not_keep_the_stop():
    """The same artefact from the other side: in "7.(3)" the 7 is the marker."""
    assert _clean(". (3) The sessions divisions") == "(3) The sessions divisions"


def test_punctuation_that_belongs_to_the_text_is_left_alone():
    assert _clean("...continued") == "...continued"
    assert _clean("normal (a) text") == "normal (a) text"
    assert _clean(". and then") == ". and then"


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus not fetched")
def test_the_ingested_code_carries_no_spacing_artefacts():
    """Checked against the real act, not a fixture: the count was 27."""
    import re

    act = parse_act(
        CORPUS.read_text(encoding="utf-8", errors="replace"),
        act_id=75,
        source_url="https://bdlaws.minlaw.gov.bd/act-print-75.html",
    )
    offenders = [
        (s.number, m.group(0))
        for s in act.sections
        for m in re.finditer(r"\S\s+[,;:]", s.text)
    ]
    assert offenders == []


# --- ADR 0006: only operative law is retrievable as law -----------------------


def test_an_amending_act_is_recognised_from_its_own_title():
    """Regression. The role was an annotation nobody derived.

    `parse_act` defaulted every document to operative, so ADR 0006's guarantee —
    that an amending instrument never answers a question about what the law
    provides — rested on no one ever ingesting one.
    """
    from app.ingest import DocumentRole, infer_role

    assert infer_role("Code of Criminal Procedure (Amendment) Act, 2026") is (
        DocumentRole.AMENDING
    )
    assert infer_role("Code of Criminal Procedure (Amending) Ordinance, 1976") is (
        DocumentRole.AMENDING
    )
    assert infer_role("The Code of Criminal Procedure, 1898") is DocumentRole.OPERATIVE
    assert infer_role("The Penal Code, 1860") is DocumentRole.OPERATIVE
    assert infer_role("") is DocumentRole.OPERATIVE


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus not fetched")
def test_the_ingested_code_is_operative():
    from app.ingest import DocumentRole

    act = parse_act(
        CORPUS.read_text(encoding="utf-8", errors="replace"),
        act_id=75,
        source_url="https://bdlaws.minlaw.gov.bd/act-print-75.html",
    )
    assert act.role is DocumentRole.OPERATIVE


def test_an_explicit_role_overrides_the_inference():
    from app.ingest import DocumentRole

    act = parse_act(
        FIXTURE.read_text(encoding="utf-8"),
        act_id=1,
        source_url="x",
        role=DocumentRole.AMENDING,
    )
    assert act.role is DocumentRole.AMENDING
