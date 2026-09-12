"""Request and response models for the public API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' when the service is serving requests")
    environment: str
    version: str


class ProviderInfo(BaseModel):
    name: str = Field(description="Configured provider, e.g. 'groq' or 'ollama'")
    chat_model: str
    capabilities: list[str] = Field(
        description="Declared capabilities: text, vision, transcription"
    )
    reachable: bool | None = Field(
        default=None,
        description="Live reachability; null when not probed on this request",
    )


class ProviderChoice(BaseModel):
    """A model the deployment can actually answer with."""

    name: str = Field(description="'groq' or 'ollama'")
    label: str = Field(description="How to show it to a reader")
    model: str
    available: bool
    note: str = Field(default="", description="Why it is unavailable, when it is")


class MetaResponse(BaseModel):
    """What the deployed system is and what it can currently do.

    The frontend reads this on load to decide which input modalities to offer,
    rather than hardcoding assumptions about the deployment.
    """

    app_name: str
    version: str
    provider: ProviderInfo
    providers: list[ProviderChoice] = Field(
        default_factory=list,
        description=(
            "Every model this deployment can answer with. The interface reads this "
            "rather than assuming: a hosted deployment usually has no local model, "
            "and offering a switch to one that is not there is worse than offering "
            "no switch."
        ),
    )
    features: list[str] = Field(
        default_factory=list,
        description=(
            "Input modalities this deployment can actually serve: text, speech, "
            "image, upload. The interface offers only these, rather than showing a "
            "control that fails on use."
        ),
    )
    disclaimer: str
    source_attribution: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    document_id: str | None = Field(
        default=None,
        description=(
            "An uploaded document to answer against, from POST /api/documents. "
            "Its text is supplied to the model alongside the statute and is never "
            "treated as law."
        ),
    )
    language: str = Field(
        default="en", description="ISO code of the question's language; 'bn' for Bangla"
    )
    provider: str | None = Field(
        default=None,
        description=(
            "Which model answers: 'groq' for the hosted one, 'ollama' for a local "
            "one. Omitted means the deployment's default. Only providers listed in "
            "/api/meta as available will answer."
        ),
    )


class AmendmentOut(BaseModel):
    """How a cited section came to read as it does.

    Returned with the citation because current wording is not the whole answer to a
    legal question. A provision substituted with effect from a date after the events
    a user is asking about is the wrong provision for those events, and nothing in
    the text itself says so.
    """

    operation: str = Field(description="substituted, inserted, omitted, repealed")
    text: str = Field(description="The footnote as published, unedited")
    amending_act_title: str | None = None
    amending_act_id: int | None = None
    act_number: str | None = Field(default=None, description="e.g. 'XI of 2026'")
    effective_from: str | None = Field(
        default=None, description="ISO date, null when the footnote does not state one"
    )
    source_url: str = Field(default="", description="The amending act on bdlaws")


class OffenceOut(BaseModel):
    """The Schedule II row a Schedule II citation names.

    Returned alongside the excerpt because the excerpt is one line of a table and
    the model chooses which line. Asked whether theft is bailable it has quoted
    the cognizability line: verbatim, verified, and not the answer. These columns
    come from the parse, so the row can be shown in full rather than selected
    from — an explanation that cannot drift from the source because no model
    wrote it.

    Each attribute is "yes", "no", "depends" or "unknown". "depends" is the
    schedule's own answer for entries that read "according as the offence abetted
    is bailable or not"; recording it as "no" would be a wrong answer rather than
    an honest one.
    """

    cognizable: str = Field(description="yes | no | depends | unknown")
    bailable: str = Field(description="yes | no | depends | unknown")
    compoundable: str = Field(description="yes | no | depends | unknown")
    triable_by: str = Field(default="", description="The court that tries it")
    punishment: str = Field(default="", description="As stated in the schedule")
    warrant_or_summons: str = Field(
        default="", description="Whether process issues in the first instance"
    )


class CitationOut(BaseModel):
    section: str = Field(description="Section number, e.g. '54' or '561A'")
    source: str = Field(
        default="CrPC",
        description=(
            "Which document the section number belongs to. Penal Code section 379 "
            "is theft; CrPC section 379 is not, so the number alone is ambiguous."
        ),
    )
    marginal_note: str = ""
    part: str | None = None
    chapter: str | None = None
    quote: str = Field(
        default="",
        description="Verbatim excerpt, empty when no quotation could be verified",
    )
    quote_verified: bool = Field(
        description="True only when the excerpt was found in the stored source text"
    )
    source_url: str
    offence: OffenceOut | None = Field(
        default=None,
        description=(
            "The Schedule II row, for citations to Schedule II. Null for sections "
            "of an act, which are prose rather than a table."
        ),
    )
    amendments: list[AmendmentOut] = Field(
        default_factory=list,
        description=(
            "Amendments to this section, most recent first, undated last. Empty for "
            "Schedule II rows and uploaded documents, which carry no footnotes."
        ),
    )


class DroppedCitation(BaseModel):
    section: str
    reason: str
    source: str = "CrPC"
    quote: str | None = None


class AskResponse(BaseModel):
    """An answer, or a refusal, with everything needed to check it.

    `question_text` is echoed back because a question may have arrived as speech or
    an image and been converted to text. A conversion error otherwise becomes a
    retrieval failure with no visible cause.
    """

    question_text: str
    answer: str
    refused: bool
    reason: str = ""
    citations: list[CitationOut] = Field(default_factory=list)
    dropped_citations: list[DroppedCitation] = Field(
        default_factory=list,
        description="Citations the validator could not substantiate, and why",
    )
    retrieved_sections: list[str] = Field(default_factory=list)
    model: str = ""
    cached: bool = Field(
        default=False,
        description=(
            "True when served from cache. Generation is deterministic, so a cached "
            "answer is the same answer, obtained without spending provider budget."
        ),
    )
    disclaimer: str


class TranslateRequest(BaseModel):
    """Translate an answer's explanation.

    Only the explanation is accepted. Statutory excerpts are deliberately not
    translatable through this endpoint: a quotation is shown with a claim that it
    was verified verbatim against the source, and that claim cannot survive
    translation.
    """

    text: str = Field(min_length=1, max_length=8000)
    target: str = Field(default="bn", description="'bn' for Bangla, 'en' for English")


class TranslateResponse(BaseModel):
    text: str
    target: str
    model: str = ""
    notice: str = Field(
        description="Shown with the translation: machine-generated, not the source"
    )


class TranscriptionResponse(BaseModel):
    """Speech converted to a question.

    The text is returned rather than answered directly. A transcription error would
    otherwise become a retrieval failure with no visible cause — the user asked one
    thing, the system answered another, and nothing in the reply reveals the
    substitution. Returning it lets the caller see and correct what was heard before
    committing to an answer.
    """

    text: str
    language: str | None = Field(
        default=None, description="Language hint that was passed to the model, if any"
    )
    model: str = ""
    seconds: float = Field(description="Wall-clock time spent transcribing")


class DocumentResponse(BaseModel):
    """An uploaded document, ready to ask questions against.

    Uploading does not add anything to the legal corpus. The document is held in
    memory for this deployment's lifetime and is used only to answer questions that
    name it — it has no authority, and the system has no way to establish any.
    """

    document_id: str
    filename: str
    pages: int
    characters: int
    preview: str = Field(description="Opening of the extracted text, for confirmation")
    notice: str


class ImageTextResponse(BaseModel):
    """Text read out of an image.

    Returned rather than answered, for the same reason as a transcription: an OCR
    error would otherwise become a retrieval failure with no visible cause.
    """

    text: str
    languages: str = Field(description="Languages tesseract was asked to recognise")
    seconds: float
