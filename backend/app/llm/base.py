"""Provider-neutral interface for language model access.

Call sites depend on this module and never on a concrete provider. Providers differ
in what they can do, so capabilities are declared explicitly rather than discovered
by calling a method and catching the failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

Role = Literal["system", "user", "assistant"]


class Capability(StrEnum):
    TEXT = "text"
    VISION = "vision"
    TRANSCRIPTION = "transcription"


class CapabilityUnavailable(RuntimeError):
    """Raised when a provider is asked for something it does not support.

    Callers are expected to degrade the feature rather than fail the request.
    """

    def __init__(self, provider: str, capability: Capability) -> None:
        super().__init__(f"provider {provider!r} does not support {capability.value}")
        self.provider = provider
        self.capability = capability


class ProviderUnavailable(RuntimeError):
    """Raised when a provider is configured but cannot currently be reached."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Why the model stopped. "length" means it ran out of budget mid-sentence,
    # which is a different failure from anything it chose to say and has to be
    # told apart from one: a reply cut off before its closing brace parses as
    # prose, produces no citations, and is then indistinguishable from a model
    # that simply failed to cite.
    finish_reason: str | None = None


class LLMProvider(ABC):
    """A language model backend."""

    name: str

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[Capability]:
        """What this provider can do, as configured."""

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def require(self, capability: Capability) -> None:
        if not self.supports(capability):
            raise CapabilityUnavailable(self.name, capability)

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        """Generate a completion for a chat exchange."""

    async def transcribe(
        self, audio: bytes, filename: str, *, language: str | None = None
    ) -> str:
        """Transcribe speech to text. Override where supported."""
        raise CapabilityUnavailable(self.name, Capability.TRANSCRIPTION)

    async def read_image(self, image: bytes, mime_type: str, prompt: str) -> str:
        """Extract text or a description from an image. Override where supported."""
        raise CapabilityUnavailable(self.name, Capability.VISION)

    async def health(self) -> bool:
        """Whether the provider is reachable right now."""
        try:
            await self.complete(
                [ChatMessage(role="user", content="ping")], max_tokens=1
            )
        except Exception:
            return False
        return True
