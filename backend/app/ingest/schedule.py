"""Parser for Schedule II of the Code of Criminal Procedure.

Schedule II is published as a 161-page PDF, separately from the act text, and it is
load-bearing: sections 4(1)(b) and 4(1)(f) define "bailable offence" and "cognizable
offence" by reference to it. Questions of the form "is theft bailable?" or "can the
police arrest without a warrant for criminal breach of trust?" are answered by this
table and by nothing else in the corpus.

Three properties of the document drive the design.

The table has eight columns but its borders are drawn as thin rectangles rather than
lines, and the column positions shift from page to page. Boundaries are therefore
derived per page from the rectangles rather than assumed.

There are no horizontal rules, so rows are not delimited at all. A record begins on
the line where the Section column has text and continues through every following
line where it does not — the same shape as the marginal-note continuation in the main
act parser.

Many cells read "Ditto", meaning the value above. Left unresolved, an entry says
nothing; resolved wrongly, it says something false about a different offence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pdfplumber

from app.ingest.models import ScheduleEntry, Triable

# "379.", "411.", "120B.", "302"
SECTION_CELL = re.compile(r"^(\d{1,3}[A-Z]{0,3})\s*\.?$")
RUNNING_HEAD = re.compile(r"Criminal\s+Procedure|1898:\s*Act", re.I)
COLUMN_NUMBERS = re.compile(r"^[1-8](\s+[1-8])+$")
CHAPTER = re.compile(r"CHAPTER\s+[IVXL]+[A-Z]*", re.I)
DITTO = re.compile(r"^\s*ditto\b", re.I)

# Amendment apparatus inside a cell: "4[Metropolitan Magistrate]" marks text
# substituted by the amendment at footnote 4. The markers are stripped from cell
# text because Schedule II's footnotes are not resolvable per row — they are page
# footnotes, and the table gives no way to attach one to a particular entry. Keeping
# the brackets would leave "Judicial Magistrate]." in an answer; keeping the digits
# would put a number in front of a court's name.
AMENDMENT_MARK = re.compile(r"\d*\[|\]")
STAR_OMISSION = re.compile(r"\s*\[?\s*\*\s*\*\s*\*\s*\]?\s*")

_YES_COGNIZABLE = re.compile(r"\bmay\s+arrest\b", re.I)
_NO_COGNIZABLE = re.compile(r"\b(?:shall\s+not|may\s+not)\s+arrest\b", re.I)
_DEPENDS = re.compile(r"accor[- ]?ding\s+as|\bditto\b", re.I)


@dataclass(slots=True)
class _Record:
    cells: list[str] = field(default_factory=lambda: [""] * 8)
    page: int = 0

    def extend(self, line: list[str]) -> None:
        for index, text in enumerate(line):
            # The section number is set once, when the record opens, and never
            # extended. Continuation lines sometimes carry a stray mark in that
            # column — a period rendered as its own word — which appended to the
            # number turns "119" into "119 ." and splits one offence into two keys.
            if index == 0 or not text:
                continue
            current = self.cells[index]
            if not current:
                self.cells[index] = text
            elif current.endswith("-"):
                # Line-break hyphenation: "compoun-" + "dable" is one word.
                self.cells[index] = current[:-1] + text
            else:
                self.cells[index] = f"{current} {text}"


@dataclass(frozen=True, slots=True)
class _Grid:
    """Where the table sits on a page: its columns, and where it stops.

    The bottom edge matters as much as the columns. Pages carry amendment
    footnotes below the table, and a footnote begins with its marker digit — which
    sits in the Section column and looks exactly like a section number. Parsed as
    table rows they create entries such as section "1 The words", and worse, they
    swallow the real entry above them: section 420 was lost this way, its Section
    cell ending up as "420 1 The the of".
    """

    columns: list[tuple[float, float]]
    bottom: float


def _column_bounds(page) -> _Grid | None:
    """The table's column x-ranges and bottom edge, from its border rectangles."""
    vertical = [
        r
        for r in page.rects
        if (r["x1"] - r["x0"]) < 3 and (r["bottom"] - r["top"]) > 40
    ]
    centres = sorted({round((r["x0"] + r["x1"]) / 2, 1) for r in vertical})
    if len(centres) != 7:
        return None

    words = page.extract_words()
    if not words:
        return None

    edges = [
        min(w["x0"] for w in words) - 3,
        *centres,
        max(w["x1"] for w in words) + 3,
    ]
    return _Grid(
        columns=list(zip(edges[:-1], edges[1:], strict=True)),
        bottom=_footnote_rule(page) or page.height,
    )


def _footnote_rule(page) -> float | None:
    """Where the footnotes start: the short rule drawn above them.

    The obvious boundary — the bottom of the column border rectangles — is wrong.
    Those rectangles are drawn in segments rather than running the table's full
    height, so their lowest edge sits well above the last row and using it discarded
    roughly a third of every page.

    The separator rule is short, horizontal, and in the lower half of the page. 124
    of the 161 pages carry one; the rest have no footnotes at all.
    """
    candidates = [
        line["top"]
        for line in page.lines
        if abs(line["top"] - line["bottom"]) < 2
        and (line["x1"] - line["x0"]) < page.width * 0.6
        and line["top"] > page.height * 0.4
    ]
    return min(candidates, default=None)


def _lines(page, grid: _Grid) -> list[list[str]]:
    """Words grouped into visual lines, each split across the eight columns.

    Words below the table's bottom edge are footnotes and are dropped.
    """
    bounds = grid.columns
    buckets: dict[int, list[dict]] = {}
    for word in page.extract_words():
        if word["top"] >= grid.bottom:
            continue
        buckets.setdefault(round(word["top"] / 3), []).append(word)

    lines = []
    for key in sorted(buckets):
        cells = [""] * len(bounds)
        for word in sorted(buckets[key], key=lambda w: w["x0"]):
            midpoint = (word["x0"] + word["x1"]) / 2
            for index, (low, high) in enumerate(bounds):
                if low <= midpoint < high:
                    cells[index] = f"{cells[index]} {word['text']}".strip()
                    break
        lines.append(cells)
    return lines


# The column headings, repeated at the top of all 161 pages. Matched per cell
# rather than against the joined line: the heading block sometimes carries a stray
# number in the Section column, which stopped the line being recognised as a heading
# and left "Offence." recorded as the offence for section 392.
HEADING_CELLS = frozenset(
    {"section.", "section", "offence.", "offence", "not.", "instance."}
)
HEADING_PHRASES = re.compile(
    r"whether\s+the\s+police|whether\s+a\s+warrant|whether\s+bailable"
    r"|whether\s+compoun|punishment\s+under\s+the|by\s+what\s+court",
    re.I,
)


def _is_noise(cells: list[str]) -> bool:
    joined = " ".join(c for c in cells if c).strip()
    if not joined:
        return True
    if COLUMN_NUMBERS.match(joined):
        return True
    if RUNNING_HEAD.search(joined):
        # A running head is a running head whatever sits in the Section column.
        # Left-hand pages print the page number first — "292 Criminal Procedure
        # [1898: Act V" — so it lands in that column and reads as a section number.
        # Every bogus entry this produced was exactly page + 281.
        return True
    if HEADING_PHRASES.search(joined):
        return True
    populated = [c.strip().lower() for c in cells if c.strip()]
    return bool(populated) and all(c in HEADING_CELLS for c in populated)


def _triable(text: str, *, yes: re.Pattern[str], no: re.Pattern[str]) -> Triable:
    if not text.strip():
        return Triable.UNKNOWN
    if _DEPENDS.search(text):
        return Triable.DEPENDS
    if no.search(text):
        return Triable.NO
    if yes.search(text):
        return Triable.YES
    return Triable.UNKNOWN


def _cognizable(text: str) -> Triable:
    return _triable(text, yes=_YES_COGNIZABLE, no=_NO_COGNIZABLE)


def _plain(text: str, word: str) -> Triable:
    """Columns that read simply "Bailable" / "Not bailable"."""
    if not text.strip():
        return Triable.UNKNOWN
    if _DEPENDS.search(text):
        return Triable.DEPENDS
    if re.search(rf"\bnot\s+{word}", text, re.I):
        return Triable.NO
    if re.search(rf"\b{word}", text, re.I):
        return Triable.YES
    return Triable.UNKNOWN


def _clean_cell(text: str) -> str:
    """Remove the amendment apparatus from a cell's text."""
    without_omissions = STAR_OMISSION.sub(" ", text)
    return re.sub(r"\s{2,}", " ", AMENDMENT_MARK.sub("", without_omissions)).strip()


def _resolve_ditto(value: str, previous: str | None) -> str:
    """Replace a "Ditto" cell with the value it points at.

    Left unresolved an entry says nothing; resolved against the wrong predecessor it
    says something false about a different offence. Where there is no predecessor the
    cell is left as written rather than guessed.
    """
    if not DITTO.match(value):
        return value
    return previous if previous else value


def parse_schedule(pdf_path, *, max_pages: int | None = None) -> list[ScheduleEntry]:
    """Parse Schedule II into one entry per offence."""
    entries: list[ScheduleEntry] = []
    records: list[tuple[_Record, str | None]] = []
    chapter: str | None = None

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[:max_pages] if max_pages else pdf.pages
        for number, page in enumerate(pages, start=1):
            grid = _column_bounds(page)
            if grid is None:
                continue

            current: _Record | None = None
            for cells in _lines(page, grid):
                if _is_noise(cells):
                    continue

                joined = " ".join(c for c in cells if c)
                if CHAPTER.search(joined) and not SECTION_CELL.match(cells[0]):
                    match = CHAPTER.search(joined)
                    chapter = joined[match.start() :].strip()
                    current = None
                    continue

                section = SECTION_CELL.match(cells[0])
                if section:
                    current = _Record(page=number)
                    # Use the captured number, not the raw cell: the source writes
                    # "119 ." as often as "119.", and a stray space makes a
                    # distinct key for the same offence.
                    current.cells[0] = section.group(1)
                    records.append((current, chapter))
                    current.extend(cells)
                elif current is not None:
                    current.extend(cells)

    previous: list[str] = [""] * 8
    for record, record_chapter in records:
        cells = list(record.cells)
        for index in range(1, 8):
            cells[index] = _resolve_ditto(cells[index], previous[index])
        previous = cells
        cells = [cells[0], *(_clean_cell(c) for c in cells[1:])]

        entries.append(
            ScheduleEntry(
                penal_code_section=cells[0],
                offence=cells[1],
                cognizable=_cognizable(cells[2]),
                warrant_or_summons=cells[3],
                bailable=_plain(cells[4], "bailable"),
                compoundable=_plain(cells[5], "compoundable"),
                punishment=cells[6],
                triable_by=cells[7],
                chapter=record_chapter,
                page=record.page,
            )
        )
    return entries


@dataclass(frozen=True, slots=True)
class _ScheduleSection:
    """The parts of a Section the gold-label validator reads."""

    text: str
    is_repealed: bool = False


class ScheduleCorpus:
    """Schedule II behind the same interface as a parsed Act.

    Gold labels are verified by resolving them against a corpus and checking the
    text still says what the question was written against. Schedule II is a table,
    not an act, but a label pointing into it needs the same check — otherwise
    "ScheduleII-379" could rot into pointing at the wrong offence with nothing to
    notice.
    """

    def __init__(self, entries: list[ScheduleEntry]) -> None:
        self._entries = {e.penal_code_section: e for e in entries}

    def section(self, number: str) -> _ScheduleSection | None:
        entry = self._entries.get(number)
        if entry is None:
            return None
        parts = [
            entry.offence,
            f"cognizable: {entry.cognizable.value}",
            f"bailable: {entry.bailable.value}",
            f"compoundable: {entry.compoundable.value}",
            entry.triable_by,
            entry.punishment,
        ]
        return _ScheduleSection(text=" ".join(p for p in parts if p.strip()))
