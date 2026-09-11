"""Citation validation.

The last thing between a generated answer and the user. Everything upstream —
chunking, retrieval, prompting — improves the *odds* of a grounded answer. This is
the only component that can refuse to emit an ungrounded one.

Both checks are deterministic and neither asks a model whether it was honest:

  - a cited section must exist in the corpus, and must be among the sections
    retrieval actually put in front of the model;
  - a quoted excerpt must appear verbatim in the section it is attributed to.

The stage 1 baseline is why the second check exists. Of 143 quotations checked
against the sections they were attributed to, none matched — every one was fluent,
plausibly styled as statutory prose, and invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ingest.models import Act, ScheduleEntry
from app.qa.schema import CRPC, Answer
from app.retrieval.chunking import schedule_rows

SOURCE_URL = "https://bdlaws.minlaw.gov.bd/act-{act_id}/section-{number}.html"
SCHEDULE_URL = (
    "https://bdlaws.minlaw.gov.bd/upload/act/2026-05-05-11-47-47-Schedule-II.pdf"
)

# Below this length a quotation matches too easily to be evidence of anything.
MIN_QUOTE_CHARS = 20


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


@dataclass(frozen=True, slots=True)
class VerifiedCitation:
    section: str
    marginal_note: str
    part: str | None
    chapter: str | None
    quote: str
    quote_verified: bool
    source_url: str
    source: str = CRPC


@dataclass(slots=True)
class ValidationResult:
    citations: list[VerifiedCitation] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    refused: bool = False
    reason: str = ""

    @property
    def grounded(self) -> bool:
        return bool(self.citations) and not self.refused


def validate(
    answer: Answer,
    corpus: Act,
    *,
    schedule: list[ScheduleEntry] | None = None,
    retrieved_sections: list[str] | None = None,
    require_retrieved: bool = True,
) -> ValidationResult:
    """Check an answer's citations, dropping any that cannot be substantiated."""
    result = ValidationResult(refused=answer.refused)
    if answer.refused:
        result.reason = "the model declined to answer"
        return result

    allowed = set(retrieved_sections or answer.retrieved_sections)
    # Rows are re-rendered from the parsed entries so a quotation is checked against
    # the same text the model was shown.
    schedule_text = {
        chunk.section_number: chunk.text for chunk in schedule_rows(schedule or [])
    }
    schedule_by_section = {e.penal_code_section: e for e in (schedule or [])}

    for citation in answer.citations:
        number = citation.normalized
        if number is None:
            result.dropped.append(
                {"section": citation.section, "reason": "unparseable section reference"}
            )
            continue

        is_schedule = citation.is_schedule
        document = citation.document

        if is_schedule:
            entry = schedule_by_section.get(number)
            if entry is None:
                result.dropped.append(
                    {
                        "section": number,
                        "source": document,
                        "reason": "no such offence in Schedule II",
                    }
                )
                continue
            body = schedule_text.get(number, "")
            note = entry.offence.strip().rstrip(".")
            part, chapter = None, entry.chapter
            url = SCHEDULE_URL
        else:
            section = corpus.section(number)
            if section is None:
                result.dropped.append(
                    {
                        "section": number,
                        "source": document,
                        "reason": "no such section in the corpus",
                    }
                )
                continue
            body = section.text
            note = section.marginal_notes[0] if section.marginal_notes else ""
            part, chapter = section.part, section.chapter
            url = SOURCE_URL.format(act_id=corpus.act_id, number=number)

        if require_retrieved and allowed and f"{document}:{number}" not in allowed:
            # The model produced a section it was never shown. Whether or not the
            # section is real, the answer is not grounded in retrieved text.
            result.dropped.append(
                {
                    "section": number,
                    "source": document,
                    "reason": "not present in the retrieved context",
                }
            )
            continue

        quote = citation.quote.strip()
        verified = False
        if len(_normalize(quote)) >= MIN_QUOTE_CHARS:
            verified = _normalize(quote) in _normalize(body)
            if not verified:
                # Drop the quotation but keep the citation: a fabricated quotation
                # is worse than none, while the section reference may still be sound.
                result.dropped.append(
                    {
                        "section": number,
                        "source": document,
                        "reason": "quoted text does not appear in the section",
                        "quote": quote[:160],
                    }
                )
                quote = ""

        result.citations.append(
            VerifiedCitation(
                section=number,
                marginal_note=note,
                part=part,
                chapter=chapter,
                quote=quote,
                quote_verified=verified,
                source_url=url,
                source=document,
            )
        )

    if not result.citations:
        # An answer with nothing substantiated behind it is not an answer this
        # system is willing to give.
        result.refused = True
        result.reason = (
            "No citation in the answer could be verified against the retrieved "
            "statutory text, so the answer was withheld."
        )

    return result
