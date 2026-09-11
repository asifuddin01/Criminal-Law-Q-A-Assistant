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


class MetaResponse(BaseModel):
    """What the deployed system is and what it can currently do.

    The frontend reads this on load to decide which input modalities to offer,
    rather than hardcoding assumptions about the deployment.
    """

    app_name: str
    version: str
    provider: ProviderInfo
    disclaimer: str
    source_attribution: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    language: str = Field(
        default="en", description="ISO code of the question's language; 'bn' for Bangla"
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
