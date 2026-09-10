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
    disclaimer: str
