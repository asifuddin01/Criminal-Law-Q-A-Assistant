"""Schedule II parser tests.

Schedule II answers the questions the act text cannot — sections 4(1)(b) and 4(1)(f)
define "bailable" and "cognizable" by reference to it — so an offence recorded wrongly
here produces a confident, well-cited, wrong answer about whether someone can be
arrested or released.

Each test below pins a defect found by comparing output against the document.
"""

from __future__ import annotations

import pathlib

import pytest

from app.ingest.models import Triable
from app.ingest.schedule import parse_schedule

SCHEDULE = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "crpc-schedule-ii.pdf"
)
schedule_only = pytest.mark.skipif(
    not SCHEDULE.exists(),
    reason="Schedule II not fetched; run: python -m app.ingest --schedule",
)


@pytest.fixture(scope="module")
def entries():
    if not SCHEDULE.exists():
        return []
    return parse_schedule(SCHEDULE)


@schedule_only
def test_entry_count_from_the_snapshot(entries):
    assert len(entries) == 376
    assert len({e.penal_code_section for e in entries}) == 362


@schedule_only
def test_running_heads_are_not_parsed_as_offences(entries):
    """Left-hand pages print the page number first, so it lands in the Section
    column and reads as a section number: printed page 292 on PDF page 11 produced
    an entry for "section 292".

    The page-number offset is a constant 281, but a section number may legitimately
    coincide with it — section 356 really does appear on page 75. The symptom to
    assert is therefore not the coincidence but its consequence: a running head
    parsed as a row has no offence text, because a page number is all it carries.
    """
    suspects = [
        e
        for e in entries
        if int("".join(c for c in e.penal_code_section if c.isdigit())) == e.page + 281
    ]

    for entry in suspects:
        assert len(entry.offence.strip()) > 3, (
            f"section {entry.penal_code_section} on page {entry.page} has no offence "
            "text — it is the page number from the running head"
        )


@schedule_only
def test_footnotes_are_not_parsed_as_offences(entries):
    """A footnote opens with its marker digit, which sits in the Section column.
    Section 420 was lost this way, its key becoming '420 1 The the of'."""
    for entry in entries:
        assert entry.penal_code_section.strip() == entry.penal_code_section
        assert " " not in entry.penal_code_section


@schedule_only
def test_section_numbers_are_normalised(entries):
    """The source writes "119 ." as often as "119."; a stray space made two keys
    for one offence."""
    import re

    pattern = re.compile(r"^\d{1,3}[A-Z]{0,3}$")
    bad = [e.penal_code_section for e in entries if not pattern.match(e.penal_code_section)]
    assert not bad


@schedule_only
def test_column_headings_are_not_recorded_as_offences(entries):
    """Section 392's offence was once recorded as the literal string "Offence.",
    because the heading block carried a stray number in the Section column."""
    for entry in entries:
        assert entry.offence.strip().lower() not in {"offence.", "offence", "section."}


@schedule_only
@pytest.mark.parametrize(
    ("section", "fragment", "cognizable", "bailable"),
    [
        ("302", "Murder", Triable.YES, Triable.NO),
        ("379", "Theft", Triable.YES, Triable.NO),
        ("395", "Dacoity", Triable.YES, Triable.NO),
        ("420", "Cheating", Triable.YES, Triable.YES),
        ("323", "hurt", Triable.NO, Triable.YES),
    ],
)
def test_known_offences_are_classified_correctly(
    entries, section, fragment, cognizable, bailable
):
    entry = next(e for e in entries if e.penal_code_section == section)

    assert fragment.lower() in entry.offence.lower()
    assert entry.cognizable is cognizable
    assert entry.bailable is bailable


@schedule_only
def test_a_definition_section_is_absent(entries):
    """Section 378 defines theft; section 379 punishes it. A table of offences
    lists the latter."""
    assert not any(e.penal_code_section == "378" for e in entries)


@schedule_only
def test_conditional_entries_are_recorded_as_depends_not_no(entries):
    """Many rows read "According as the offence abetted is bailable or not". That
    is genuinely conditional, and recording it as False would answer "is this
    bailable?" with a confident, wrong no."""
    depends = [e for e in entries if e.bailable is Triable.DEPENDS]

    assert len(depends) > 20


@schedule_only
def test_almost_every_entry_carries_offence_text_and_a_chapter(entries):
    assert sum(1 for e in entries if not e.offence.strip()) <= 2
    assert sum(1 for e in entries if e.chapter) >= len(entries) - 5


# --- the parsed cache ---------------------------------------------------------


def test_the_parsed_cache_round_trips_exactly(tmp_path):
    """A cache that differs from the parse is worse than no cache.

    Startup reads this instead of parsing the PDF, so anything it loses is lost
    silently and for every question thereafter.
    """
    from app.ingest import dump_entries, load_entries
    from app.ingest.models import ScheduleEntry, Triable

    entries = [
        ScheduleEntry(
            penal_code_section="379",
            offence="Theft",
            cognizable=Triable.YES,
            warrant_or_summons="Warrant",
            bailable=Triable.NO,
            compoundable=Triable.DEPENDS,
            punishment="Imprisonment for 3 years",
            triable_by="Judicial Magistrate",
            chapter="XVII",
            page=42,
        ),
        ScheduleEntry(
            penal_code_section="511",
            offence="Attempt — অপরাধ",
            cognizable=Triable.UNKNOWN,
            bailable=Triable.DEPENDS,
        ),
    ]

    path = dump_entries(entries, tmp_path / "schedule.json")
    loaded = load_entries(path)

    assert [e.model_dump() for e in loaded] == [e.model_dump() for e in entries]
    # The tri-state columns survive as themselves, not as booleans: "depends" is
    # a real answer in this schedule and collapsing it would be a wrong one.
    assert loaded[0].compoundable is Triable.DEPENDS
    assert loaded[1].cognizable is Triable.UNKNOWN
    # Bangla in an offence name survives the round trip.
    assert "অপরাধ" in loaded[1].offence


@pytest.mark.skipif(not SCHEDULE.exists(), reason="Schedule II not fetched")
def test_the_cache_matches_a_fresh_parse_of_the_real_pdf():
    """Checked against the actual 161-page source, not a fixture."""
    from app.ingest import load_entries, parsed_schedule_path

    if not parsed_schedule_path().exists():
        pytest.skip("cache not built; run: python -m app.ingest.precompute")

    cached = load_entries(parsed_schedule_path())
    fresh = parse_schedule(SCHEDULE)

    assert [e.model_dump() for e in cached] == [e.model_dump() for e in fresh]
