"""Chunking strategies.

Two are implemented so they can be compared rather than argued about. Stage 2 uses
the naive one deliberately: the legal-aware chunker in stage 3 has to earn its place
against a measurement, not against an assertion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingest.models import Act


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

    @property
    def citation(self) -> str:
        return self.section_number


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


STRATEGIES = {"naive_fixed_size": naive_fixed_size, "legal_aware": legal_aware}
