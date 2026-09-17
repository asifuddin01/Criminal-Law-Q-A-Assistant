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
from app.qa.quoting import MIN_QUOTE_CHARS, canonical, check_quote
from app.qa.schema import CRPC, UPLOADED, Answer
from app.retrieval.chunking import schedule_rows

SOURCE_URL = "https://bdlaws.minlaw.gov.bd/act-{act_id}/section-{number}.html"
AMENDING_ACT_URL = "https://bdlaws.minlaw.gov.bd/act-details-{act_id}.html"
DISPLAY = {"CrPC": "Code of Criminal Procedure", "PenalCode": "Penal Code"}
SCHEDULE_URL = (
    "https://bdlaws.minlaw.gov.bd/upload/act/2026-05-05-11-47-47-Schedule-II.pdf"
)

@dataclass(frozen=True, slots=True)
class AmendmentNote:
    """How a cited section came to read as it does.

    Surfaced with the citation because a section's current wording is not the whole
    answer to a legal question: when it changed, under which act, and from what date
    decide whether it governs the matter the user is actually asking about. The
    parser has carried these records since ingestion; nothing showed them.
    """

    operation: str
    text: str
    amending_act_title: str | None = None
    amending_act_id: int | None = None
    act_number: str | None = None
    effective_from: str | None = None
    source_url: str = ""


@dataclass(frozen=True, slots=True)
class OffenceFacts:
    """The Schedule II row behind a Schedule II citation.

    A row is a table, and a model quoting it quotes one line of it. Which line it
    picks is a choice it can get wrong: asked whether theft is bailable, the local
    model quoted the cognizability line — verbatim, verified, and not the answer.
    The reader was left with a one-sentence conclusion and an excerpt about
    something else.

    The columns are parsed at ingestion, so they can be shown rather than
    selected. What the table says about the offence is then displayed in full,
    from the parse, and the explanation stops depending on a 3B model picking the
    right sentence out of a table. Nothing here is generated.
    """

    cognizable: str
    bailable: str
    compoundable: str
    triable_by: str = ""
    punishment: str = ""
    warrant_or_summons: str = ""


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
    # Set when the quotation verified only after a label was trimmed or an elision
    # was read as one. Surfaced so a repaired quotation is never mistaken for one
    # the model produced cleanly.
    quote_repair: str = ""
    # Amendments attached to this section, most recent first.
    amendments: tuple[AmendmentNote, ...] = ()
    # The Schedule II row this citation names, for citations that name one.
    offence: OffenceFacts | None = None


@dataclass(slots=True)
class ValidationResult:
    citations: list[VerifiedCitation] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    refused: bool = False
    reason: str = ""

    @property
    def repaired_quotes(self) -> int:
        """Quotations that verified only after an allowance was made."""
        return sum(1 for c in self.citations if c.quote_repair)

    @property
    def grounded(self) -> bool:
        return bool(self.citations) and not self.refused


def _amendment_notes(act: Act, section) -> tuple[AmendmentNote, ...]:
    """Amendment records for a section, most recent first.

    Ordered by effective date because that is the order a reader needs: the most
    recent change is the one that decides how the section reads today. Records
    without a date sort last rather than being dropped — the footnote text still
    says what changed, and discarding it would hide an amendment because its date
    failed to parse.
    """
    notes = [
        AmendmentNote(
            operation=str(a.operation),
            text=a.text,
            amending_act_title=a.amending_act_title,
            amending_act_id=a.amending_act_id,
            act_number=a.act_number,
            effective_from=a.effective_from.isoformat() if a.effective_from else None,
            source_url=(
                AMENDING_ACT_URL.format(act_id=a.amending_act_id)
                if a.amending_act_id
                else ""
            ),
        )
        for a in act.amendments_for(section)
    ]
    # Dated records first, most recent among them first; undated records last.
    notes.sort(
        key=lambda n: (n.effective_from is not None, n.effective_from or ""),
        reverse=True,
    )
    return tuple(notes)


def validate(
    answer: Answer,
    corpora: Act | dict[str, Act],
    *,
    schedule: list[ScheduleEntry] | None = None,
    uploaded: dict[str, str] | None = None,
    retrieved_sections: list[str] | None = None,
    require_retrieved: bool = True,
) -> ValidationResult:
    """Check an answer's citations, dropping any that cannot be substantiated.

    `corpora` maps a document code to the parsed act it names. A single Act is
    accepted as the Code, which is what it meant when there was only one act — but a
    citation is now resolved against the document it claims, because section numbers
    repeat across acts and resolving one against another would confirm a wrong
    citation as readily as a right one.
    """
    acts = corpora if isinstance(corpora, dict) else {CRPC: corpora}
    result = ValidationResult(refused=answer.refused)
    if answer.refused:
        # The model's own words are the reason, and the reader needs them. Asked
        # something it cannot answer, the model says what is missing — or, for an
        # ambiguous question, asks which offence or proceeding is meant. Replacing
        # that with a fixed "the model declined to answer" threw away the one
        # sentence that tells a reader what to do next, in both interfaces.
        result.reason = answer.text.strip() or "the model declined to answer"
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

        if document == UPLOADED:
            body = (uploaded or {}).get(number, "")
            if not body:
                result.dropped.append(
                    {
                        "section": number,
                        "source": document,
                        "reason": "no such passage in the uploaded document",
                    }
                )
                continue
            note = "uploaded document"
            part, chapter, url = None, None, ""
            amendments = ()
            offence = None
        elif is_schedule:
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
            # Schedule II is a table, not a section; its rows carry no footnotes.
            amendments = ()
            offence = OffenceFacts(
                cognizable=str(entry.cognizable),
                bailable=str(entry.bailable),
                compoundable=str(entry.compoundable),
                triable_by=entry.triable_by.strip(),
                punishment=entry.punishment.strip(),
                warrant_or_summons=entry.warrant_or_summons.strip(),
            )
        else:
            act = acts.get(document)
            if act is None:
                result.dropped.append(
                    {
                        "section": number,
                        "source": document,
                        "reason": f"{document} is not part of the ingested corpus",
                    }
                )
                continue
            section = act.section(number)
            if section is None:
                result.dropped.append(
                    {
                        "section": number,
                        "source": document,
                        "reason": (
                            f"no section {number} in the "
                            f"{DISPLAY.get(document, document)}"
                        ),
                    }
                )
                continue
            body = section.text
            note = section.marginal_notes[0] if section.marginal_notes else ""
            part, chapter = section.part, section.chapter
            url = SOURCE_URL.format(act_id=act.act_id, number=number)
            amendments = _amendment_notes(act, section)
            offence = None

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
        repair = ""
        if len(canonical(quote)) >= MIN_QUOTE_CHARS:
            checked = check_quote(quote, body, marginal_note=note)
            verified, repair = checked.verified, checked.repair
            if verified:
                # What is displayed is what verified, not what the model wrote: a
                # label copied in front of the text is removed rather than shown to
                # the user as part of the statute.
                quote = checked.quote
            else:
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
                quote_repair=repair,
                amendments=amendments,
                offence=offence,
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
