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
