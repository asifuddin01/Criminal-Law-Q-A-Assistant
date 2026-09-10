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

from app.ingest.models import Act
from app.qa.schema import Answer

SOURCE_URL = "https://bdlaws.minlaw.gov.bd/act-{act_id}/section-{number}.html"

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
    retrieved_sections: list[str] | None = None,
    require_retrieved: bool = True,
) -> ValidationResult:
    """Check an answer's citations, dropping any that cannot be substantiated."""
    result = ValidationResult(refused=answer.refused)
    if answer.refused:
        result.reason = "the model declined to answer"
        return result

    allowed = set(retrieved_sections or answer.retrieved_sections)

    for citation in answer.citations:
        number = citation.normalized
        if number is None:
            result.dropped.append(
                {"section": citation.section, "reason": "unparseable section reference"}
            )
            continue

        section = corpus.section(number)
        if section is None:
            result.dropped.append(
                {"section": number, "reason": "no such section in the corpus"}
            )
            continue

        if require_retrieved and allowed and number not in allowed:
            # The model produced a section it was never shown. Whether or not the
            # section is real, the answer is not grounded in retrieved text.
            result.dropped.append(
                {"section": number, "reason": "not present in the retrieved context"}
            )
            continue

        quote = citation.quote.strip()
        verified = False
        if len(_normalize(quote)) >= MIN_QUOTE_CHARS:
            verified = _normalize(quote) in _normalize(section.text)
            if not verified:
                # Drop the quotation but keep the citation: a fabricated quotation
                # is worse than none, while the section reference may still be sound.
                result.dropped.append(
                    {
                        "section": number,
                        "reason": "quoted text does not appear in the section",
                        "quote": quote[:160],
                    }
                )
                quote = ""

        result.citations.append(
            VerifiedCitation(
                section=number,
                marginal_note=section.marginal_notes[0] if section.marginal_notes else "",
                part=section.part,
                chapter=section.chapter,
                quote=quote,
                quote_verified=verified,
                source_url=SOURCE_URL.format(act_id=corpus.act_id, number=number),
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
