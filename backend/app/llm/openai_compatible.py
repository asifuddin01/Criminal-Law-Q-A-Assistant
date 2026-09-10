"""Shared implementation for providers exposing an OpenAI-compatible API.

Groq and Ollama both speak this protocol, so a single client covers generation,
transcription and vision across both. Providers differ only in base URL, model
names and declared capabilities.
"""

from __future__ import annotations

import base64

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from app.llm.base import (
    Capability,
    ChatMessage,
    Completion,
    LLMProvider,
    ProviderUnavailable,
)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        chat_model: str,
        capabilities: frozenset[Capability],
        vision_model: str | None = None,
        transcription_model: str | None = None,
        default_temperature: float = 0.0,
        default_max_tokens: int = 1024,
        timeout: float = 60.0,
    ) -> None:
        self.name = name
        self._chat_model = chat_model
        self._vision_model = vision_model
        self._transcription_model = transcription_model
        self._capabilities = capabilities
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    @property
    def capabilities(self) -> frozenset[Capability]:
        return self._capabilities

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        try:
            response = await self._client.chat.completions.create(
                model=self._chat_model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=(
                    self._default_temperature if temperature is None else temperature
                ),
                max_tokens=self._default_max_tokens if max_tokens is None else max_tokens,
            )
        except (APIConnectionError, APIStatusError) as exc:
            raise ProviderUnavailable(f"{self.name}: {exc}") from exc

        usage = response.usage
        return Completion(
            text=response.choices[0].message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )

    async def transcribe(
        self, audio: bytes, filename: str, *, language: str | None = None
    ) -> str:
        self.require(Capability.TRANSCRIPTION)
        assert self._transcription_model is not None
        try:
            response = await self._client.audio.transcriptions.create(
                model=self._transcription_model,
                file=(filename, audio),
                **({"language": language} if language else {}),
            )
        except (APIConnectionError, APIStatusError) as exc:
            raise ProviderUnavailable(f"{self.name}: {exc}") from exc
        return response.text.strip()

    async def read_image(self, image: bytes, mime_type: str, prompt: str) -> str:
        self.require(Capability.VISION)
        assert self._vision_model is not None
        encoded = base64.b64encode(image).decode("ascii")
        try:
            response = await self._client.chat.completions.create(
                model=self._vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                            },
                        ],
                    }
                ],
                temperature=self._default_temperature,
                max_tokens=self._default_max_tokens,
            )
        except (APIConnectionError, APIStatusError) as exc:
            raise ProviderUnavailable(f"{self.name}: {exc}") from exc
        return (response.choices[0].message.content or "").strip()
