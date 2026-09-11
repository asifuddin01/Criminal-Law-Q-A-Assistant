"""Chunking strategies.

Two are implemented so they can be compared rather than argued about. Stage 2 uses
the naive one deliberately: the legal-aware chunker in stage 3 has to earn its place
against a measurement, not against an assertion.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.ingest.models import Act

# Which document a chunk cites into. Section numbers are only unique within a
# document: Penal Code section 379 is theft, while Code of Criminal Procedure
# section 379 is about appeals. A citation carrying only "379" is ambiguous, and a
# validator checking it against the wrong document would confirm it.
CRPC = "CrPC"
SCHEDULE_II = "ScheduleII"

# Human-facing names. The codes above are identifiers — they appear in gold labels,
# in retrieved-section lists and in metrics, so they must be stable and free of
# spaces. What a reader sees is a separate concern.
DISPLAY_NAMES = {CRPC: "Code of Criminal Procedure", SCHEDULE_II: "Schedule II"}


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable unit, carrying the citation it will be attributed to."""

    chunk_id: str
    text: str
    section_number: str
    marginal_note: str
    part: str | None
    chapter: str | None
    strategy: str
    # True when the chunk's text crosses out of the section it is attributed to.
    # The naive strategy cannot avoid this; it is recorded so the cost is visible.
    crosses_section_boundary: bool = False
    document: str = CRPC

    @property
    def citation(self) -> str:
        if self.document == CRPC:
            return f"section {self.section_number}"
        return (
            f"{DISPLAY_NAMES[self.document]}, "
            f"Penal Code section {self.section_number}"
        )

    @property
    def identifier(self) -> str:
        """Stable key for gold labels and retrieval metrics."""
        return f"{self.document}:{self.section_number}"

    @property
    def content_hash(self) -> str:
        """Hash of the text alone.

        An incremental update compares this to decide what to re-embed. It covers
        the text and nothing else, because the embedding depends on the text and
        nothing else — a chunk whose part or chapter label was corrected does not
        need a new vector.
        """
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def naive_fixed_size(
    act: Act, *, size: int = 1000, overlap: int = 150
) -> list[Chunk]:
    """Fixed-size character windows over the act, ignoring section boundaries.

    This is the obvious first implementation and the one most systems ship. The act
    is flattened into one string, cut into equal windows, and each window is
    attributed to whichever section contains its starting character.

    Two consequences are deliberate and measured rather than avoided:

    A window that begins near the end of one section runs on into the next, so its
    text describes provisions it is not attributed to. A retrieved chunk can
    therefore support an answer while citing the wrong section.

    Sections shorter than the window share it with their neighbours, and sections
    longer than it are cut at arbitrary points, often mid-sentence and mid-clause.
    """
    spans: list[tuple[int, int, object]] = []
    pieces: list[str] = []
    cursor = 0
    for section in act.sections:
        text = section.text.strip()
        if not text:
            continue
        pieces.append(text)
        spans.append((cursor, cursor + len(text), section))
        cursor += len(text) + 2  # the "\n\n" join below

    document = "\n\n".join(pieces)
    step = max(1, size - overlap)

    def section_at(offset: int):
        for start, end, section in spans:
            if start <= offset < end:
                return section
        return spans[-1][2] if spans else None

    chunks: list[Chunk] = []
    for index, start in enumerate(range(0, len(document), step)):
        window = document[start : start + size]
        if not window.strip():
            continue
        owner = section_at(start)
        if owner is None:
            continue
        end_owner = section_at(min(start + len(window) - 1, len(document) - 1))
        chunks.append(
            Chunk(
                chunk_id=f"naive-{index:05d}",
                text=window,
                section_number=owner.number,
                marginal_note=owner.marginal_notes[0] if owner.marginal_notes else "",
                part=owner.part,
                chapter=owner.chapter,
                strategy="naive_fixed_size",
                crosses_section_boundary=end_owner is not owner,
            )
        )
    return chunks


def _split_at_subsections(text: str, limit: int) -> list[str]:
    """Split over-long section text at subsection boundaries, never mid-clause."""
    if len(text) <= limit:
        return [text]
    # Subsections read "(1)", "(2)"; clauses read "(a)", "(aa)".
    parts = re.split(r"(?=\(\d+\)|\((?:[a-z]{1,2})\))", text)
    out: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > limit:
            out.append(current.strip())
            current = part
        else:
            current += part
    if current.strip():
        out.append(current.strip())
    return [p for p in out if p]


def legal_aware(act: Act, *, limit: int = 1400) -> list[Chunk]:
    """One chunk per section, split at subsection boundaries when over-long.

    The section is the unit of citation (ADR 0002), so a chunk never crosses one.
    Over-long sections are split at subsection boundaries with the section's
    identity repeated into every piece, so each chunk carries what is needed to
    cite it.
    """
    chunks: list[Chunk] = []
    for section in act.sections:
        text = section.text.strip()
        if not text:
            continue
        note = section.marginal_notes[0] if section.marginal_notes else ""
        header = f"Section {section.number}. {note}".strip().rstrip(".")
        for part_index, piece in enumerate(_split_at_subsections(text, limit)):
            chunks.append(
                Chunk(
                    chunk_id=f"legal-{section.number}-{part_index}",
                    text=f"{header}\n{piece}",
                    section_number=section.number,
                    marginal_note=note,
                    part=section.part,
                    chapter=section.chapter,
                    strategy="legal_aware",
                    crosses_section_boundary=False,
                )
            )
    return chunks


def _describe(value, positive: str, negative: str, conditional: str) -> str:
    """Render a tri-state column as a sentence a reader and a model both parse.

    DEPENDS is rendered explicitly rather than omitted. Many rows genuinely read
    "according as the offence abetted is bailable or not", and silence would be read
    as "no".
    """
    return {
        "yes": positive,
        "no": negative,
        "depends": conditional,
        "unknown": "Not stated in the schedule.",
    }[value.value if hasattr(value, "value") else str(value)]


def schedule_rows(entries) -> list[Chunk]:
    """One chunk per Schedule II row, never split.

    A row associates an offence with its procedural attributes, so a chunk crossing
    a row boundary would attribute one offence's bailability to another. Rows are
    short, so no splitting is needed and none is done.

    The row is rendered as sentences rather than as a table fragment because it is
    retrieved by embedding a natural-language question: "is theft bailable" should
    land near "Theft ... This offence is bailable", not near a run of column headers.
    """
    chunks: list[Chunk] = []
    for entry in entries:
        offence = entry.offence.strip().rstrip(".") or "(offence not stated)"
        lines = [
            f"Schedule II of the Code of Criminal Procedure — "
            f"Penal Code section {entry.penal_code_section}: {offence}.",
            _describe(
                entry.cognizable,
                "This is a cognizable offence: the police may arrest without a warrant.",
                "This is a non-cognizable offence: the police may not arrest without a "
                "warrant.",
                "Whether the police may arrest without a warrant depends on the "
                "underlying offence.",
            ),
            _describe(
                entry.bailable,
                "This offence is bailable.",
                "This offence is not bailable.",
                "Whether this offence is bailable depends on the underlying offence.",
            ),
            _describe(
                entry.compoundable,
                "This offence is compoundable.",
                "This offence is not compoundable.",
                "Whether this offence is compoundable depends on the underlying "
                "offence.",
            ),
        ]
        if entry.triable_by.strip():
            lines.append(f"Triable by: {entry.triable_by.strip()}")
        if entry.punishment.strip():
            lines.append(f"Punishment under the Penal Code: {entry.punishment.strip()}")
        if entry.warrant_or_summons.strip():
            lines.append(
                f"Warrant or summons in the first instance: "
                f"{entry.warrant_or_summons.strip()}"
            )

        chunks.append(
            Chunk(
                chunk_id=f"sch2-{entry.penal_code_section}-{entry.page}",
                text="\n".join(lines),
                section_number=entry.penal_code_section,
                marginal_note=offence,
                part=None,
                chapter=entry.chapter,
                strategy="schedule_rows",
                crosses_section_boundary=False,
                document=SCHEDULE_II,
            )
        )
    return chunks


STRATEGIES = {"naive_fixed_size": naive_fixed_size, "legal_aware": legal_aware}
