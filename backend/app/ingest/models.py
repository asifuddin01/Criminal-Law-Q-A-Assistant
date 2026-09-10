"""Corpus data model.

Mirrors the entity model in docs/architecture.md. These types are the contract
between ingestion and everything downstream, so they are defined once here rather
than reconstructed per consumer.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentRole(StrEnum):
    """Why a document is in the corpus. See ADR 0006.

    Only OPERATIVE and SCHEDULE are retrievable as statements of law. An AMENDING
    document's text is a diff, not a provision, and must never answer a question
    about what the law provides.
    """

    OPERATIVE = "operative"
    AMENDING = "amending"
    SCHEDULE = "schedule"


class Operation(StrEnum):
    """What an amendment did to the text it targets."""

    INSERTED = "inserted"
    SUBSTITUTED = "substituted"
    OMITTED = "omitted"
    REPEALED = "repealed"
    ADDED = "added"
    RENUMBERED = "renumbered"
    UNKNOWN = "unknown"


class Amendment(BaseModel):
    """One footnote from the amendment apparatus, parsed into structure.

    `marker` is the document-wide footnote number that appears as a superscript at
    the point of change, which is what ties an amendment to its location in the text.
    """

    marker: int
    operation: Operation
    text: str
    amending_act_title: str | None = None
    amending_act_id: int | None = Field(
        default=None, description="bdlaws act id, from the footnote's own link"
    )
    act_number: str | None = None
    effective_from: date | None = None


class SectionUnit(BaseModel):
    """One marginal-note unit within a section.

    The source publishes a section as a sequence of these, each with its own
    marginal note. They are retained rather than flattened because the marginal
    note is the closest thing the statute has to a subheading, and it carries real
    retrieval signal.
    """

    marginal_note: str
    text: str
    footnote_markers: list[int] = Field(default_factory=list)


class Section(BaseModel):
    """A legal section: the unit of citation. See ADR 0002."""

    number: str
    part: str | None = None
    chapter: str | None = None
    heading: str | None = None
    units: list[SectionUnit] = Field(default_factory=list)
    whole_section_amended: bool = False
    is_repealed: bool = False

    @property
    def marginal_notes(self) -> list[str]:
        return [u.marginal_note for u in self.units if u.marginal_note]

    @property
    def text(self) -> str:
        return "\n\n".join(u.text for u in self.units if u.text)

    @property
    def footnote_markers(self) -> list[int]:
        return sorted({m for u in self.units for m in u.footnote_markers})

    @property
    def content_hash(self) -> str:
        """Identity of this section's text. Re-ingestion re-embeds only what changed."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class Act(BaseModel):
    """A statute, with its sections and amendment apparatus."""

    act_id: int
    title: str
    act_number: str | None = None
    role: DocumentRole = DocumentRole.OPERATIVE
    source_url: str
    fetched_at: datetime
    source_hash: str
    sections: list[Section] = Field(default_factory=list)
    amendments: dict[int, Amendment] = Field(default_factory=dict)

    def section(self, number: str) -> Section | None:
        return next((s for s in self.sections if s.number == number), None)

    def amendments_for(self, section: Section) -> list[Amendment]:
        """Amendment records attached to a section, in marker order."""
        return [
            self.amendments[m] for m in section.footnote_markers if m in self.amendments
        ]
