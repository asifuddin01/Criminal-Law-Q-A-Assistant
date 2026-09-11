"""Parser for bdlaws.minlaw.gov.bd act documents.

Operates on the single-document print view (ADR 0005), which publishes an act as an
ordered sequence of marginal-note units in a two-column layout:

    .lineremoves
      .txt-head      the marginal note
      .txt-details   the provision text

A section begins at the unit whose text opens with its number; subsequent units
without a number continue the section that is open. Part and chapter headings appear
as sibling elements in the same document order.

Four source conventions the layout does not make obvious, each of which silently
corrupts section identity if unhandled. All four are covered by tests.

1. Footnote markers are inline elements whose text is a digit. Extracting text before
   removing them puts the footnote number where the section number should be, so a
   provision opening with an amended span is read as a section named after its
   footnote. This is how section 54 goes missing.

2. A section replaced wholesale by an amendment has its number inside the amendment
   bracket: "[6.(1) Besides the Supreme Court". The bracket is meaningful and is
   recorded as `whole_section_amended`.

3. Lettered sections are usually suffixed directly (265A) but at least one hyphenates
   (265-I). Without the hyphen the section is read as a continuation and its text is
   welded onto the preceding section, which then cites it under the wrong number.

4. Sections repealed in pairs share one unit: "23 and 24. [Repealed by ...]". Both
   numbers must be emitted or the text attaches to whichever section precedes it.

5. Part and chapter headings are nested inside the row that opens them rather than
   placed before it, so they are read off the row rather than tracked by a flat
   document-order walk.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from app.ingest.models import (
    Act,
    Amendment,
    DocumentRole,
    Operation,
    Section,
    SectionUnit,
)

# A section number: digits, optionally suffixed by letters, optionally hyphenated.
_NUM = r"\d+(?:-?[A-Z]{1,3})?"

# "[6.(1) Besides" or "4. Definitions" — leading bracket marks whole-section amendment.
SECTION_START = re.compile(rf"^\s*(\[\s*)?({_NUM})\s*\.")

# "23 and 24. [Repealed by ...]" — one unit, two sections.
SECTION_PAIR = re.compile(rf"^\s*(\[\s*)?({_NUM})\s+and\s+({_NUM})\s*\.")

# Anchored deliberately. Section 4 contains "(d) [Repealed by ...]" a thousand
# characters in — a repealed *clause* inside a live section. An unanchored search
# marks the whole of section 4 repealed and removes the Code's definitions.
REPEALED_AT_START = re.compile(r"^\s*\[?\s*(?:Repealed|Omitted)\b", re.I)

_OPERATIONS: tuple[tuple[re.Pattern[str], Operation], ...] = (
    (re.compile(r"\brenumbered\b", re.I), Operation.RENUMBERED),
    (re.compile(r"\bsubstituted\b", re.I), Operation.SUBSTITUTED),
    (re.compile(r"\binserted\b", re.I), Operation.INSERTED),
    (re.compile(r"\bomitted\b", re.I), Operation.OMITTED),
    (re.compile(r"\brepealed\b", re.I), Operation.REPEALED),
    (re.compile(r"\badded\b", re.I), Operation.ADDED),
)

EFFECTIVE_FROM = re.compile(r"with effect from\s+([^)]+?)\s*\)", re.I)
_DATE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})")
ACT_NUMBER = re.compile(r"\((?:Act|Ordinance|President's Order)\s+No\.\s*([^)]+)\)", re.I)
ACT_HREF = re.compile(r"/act-(\d+)\.html")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _clean(text: str) -> str:
    """Collapse every run of whitespace, newlines and non-breaking spaces included.

    The source sets marginal notes across lines ("Short title\n\tCommencement") and
    pads text nodes with tabs, neither of which is meaningful.
    """
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _strip_markers(node: Tag) -> tuple[str, list[int]]:
    """Return the node's text with footnote markers removed, plus those markers.

    Markers must come out before text extraction, not after: their content is a bare
    digit, and a marker at the start of a provision is otherwise indistinguishable
    from a section number.
    """
    clone = BeautifulSoup(str(node), "lxml")
    markers: list[int] = []
    for span in clone.select("span.footnote"):
        raw = span.get_text(strip=True)
        if raw.isdigit():
            markers.append(int(raw))
        span.decompose()
    return _clean(clone.get_text(" ", strip=True)), markers


def _parse_effective_from(text: str) -> date | None:
    match = EFFECTIVE_FROM.search(text)
    if not match:
        return None
    parts = _DATE.search(match.group(1))
    if not parts:
        return None
    day, month_name, year = parts.groups()
    month = _MONTHS.get(month_name.lower())
    if month is None:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def _parse_operation(text: str) -> Operation:
    for pattern, operation in _OPERATIONS:
        if pattern.search(text):
            return operation
    return Operation.UNKNOWN


def _parse_amendments(soup: BeautifulSoup) -> dict[int, Amendment]:
    """Parse the footnote apparatus into structured amendment records."""
    amendments: dict[int, Amendment] = {}
    for item in soup.select("li.footnoteList"):
        marker_el = item.select_one("sup")
        if marker_el is None or not marker_el.get_text(strip=True).isdigit():
            continue
        marker = int(marker_el.get_text(strip=True))

        link = item.select_one('a[href*="/act-"]')
        act_id: int | None = None
        act_title: str | None = None
        if link is not None:
            href_match = ACT_HREF.search(link.get("href") or "")
            if href_match:
                act_id = int(href_match.group(1))
            act_title = _clean(link.get_text(" ", strip=True)) or None

        body = _clean(item.get_text(" ", strip=True))
        # Drop the leading marker digit, which is rendered inside the item.
        body = re.sub(rf"^{marker}\s+", "", body)

        act_number_match = ACT_NUMBER.search(body)

        amendments[marker] = Amendment(
            marker=marker,
            operation=_parse_operation(body),
            text=body,
            amending_act_title=act_title,
            amending_act_id=act_id,
            act_number=_clean(act_number_match.group(1)) if act_number_match else None,
            effective_from=_parse_effective_from(body),
        )
    return amendments


def _act_metadata(soup: BeautifulSoup) -> tuple[str, str | None]:
    title_el = soup.select_one("h3")
    # The heading can carry an amendment marker, which reads as part of the name:
    # the Penal Code came through as "1 The Penal Code, 1860".
    title = _strip_markers(title_el)[0] if title_el else "Unknown Act"
    title = re.sub(r"^\d+\s+(?=[A-Z])", "", title)
    number = None
    header = _clean(soup.get_text(" ", strip=True)[:800])
    match = re.search(r"\(\s*ACT\s+NO\.\s*([^)]+?)\s*\)", header, re.I)
    if match:
        number = _clean(match.group(1))
    return title, number


def parse_act(
    html: str,
    *,
    act_id: int,
    source_url: str,
    fetched_at: datetime | None = None,
    role: DocumentRole = DocumentRole.OPERATIVE,
) -> Act:
    """Parse a bdlaws print-view document into an Act."""
    soup = BeautifulSoup(html, "lxml")
    title, act_number = _act_metadata(soup)

    sections: list[Section] = []
    by_number: dict[str, Section] = {}
    part = chapter = heading = None
    current: Section | None = None

    def start(number: str, bracketed: bool) -> Section:
        section = Section(
            number=number,
            part=part,
            chapter=chapter,
            heading=heading,
            whole_section_amended=bracketed,
        )
        sections.append(section)
        by_number[number] = section
        return section

    for row in soup.select(".lineremoves"):
        # Part, chapter and section headings are nested *inside* the row that opens
        # them, not placed as siblings before it. A flat document-order walk
        # therefore reaches the row before its own heading, and the first section of
        # every part is filed with no part. Read the headings off the row first.
        part_el = row.select_one(".act-part-group")
        if part_el is not None:
            part = _strip_markers(part_el)[0]
            chapter = heading = None
        chapter_el = row.select_one(".act-chapter-group")
        if chapter_el is not None:
            chapter = _strip_markers(chapter_el)[0]
            heading = None
        heading_el = row.select_one(".act-section-head")
        if heading_el is not None:
            heading = _strip_markers(heading_el)[0]

        details = row.select_one(".txt-details")
        if details is None:
            continue

        text, markers = _strip_markers(details)
        if not text:
            continue

        head_el = row.select_one(".txt-head")
        marginal_note = _strip_markers(head_el)[0] if head_el else ""

        pair = SECTION_PAIR.match(text)
        if pair:
            # One unit, two sections: give each the same text and mark both repealed.
            remainder = text[pair.end() :]
            for number in (pair.group(2), pair.group(3)):
                section = start(number, bool(pair.group(1)))
                section.is_repealed = bool(REPEALED_AT_START.match(remainder))
                section.units.append(
                    SectionUnit(
                        marginal_note=marginal_note,
                        text=text,
                        footnote_markers=markers,
                    )
                )
            current = sections[-1]
            continue

        single = SECTION_START.match(text)
        if single:
            current = start(single.group(2), bool(single.group(1)))
            current.is_repealed = bool(REPEALED_AT_START.match(text[single.end() :]))

        if current is None:
            # Preamble or front matter before the first section.
            continue

        current.units.append(
            SectionUnit(
                marginal_note=marginal_note, text=text, footnote_markers=markers
            )
        )

    return Act(
        act_id=act_id,
        title=title,
        act_number=act_number,
        role=role,
        source_url=source_url,
        fetched_at=fetched_at or datetime.now().astimezone(),
        source_hash=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        sections=sections,
        amendments=_parse_amendments(soup),
    )
