"""Translation tests.

The provider is stubbed: these assert how the request is built and what the endpoint
guarantees, not how well a model translates.
"""

from __future__ import annotations

import pytest

from app.llm.base import Capability, ChatMessage, Completion, LLMProvider
from app.qa.translate import NOTICE, UnsupportedLanguage, translate


class RecordingProvider(LLMProvider):
    name = "recording"

    def __init__(self, reply: str = "অনুবাদ") -> None:
        self.reply = reply
        self.messages: list[ChatMessage] = []

    @property
    def capabilities(self):
        return frozenset({Capability.TEXT})

    async def complete(self, messages, *, temperature=None, max_tokens=None):
        self.messages = messages
        return Completion(text=self.reply, model="stub")


async def test_bangla_request_carries_the_legal_glossary():
    """Without it the model transliterates: 'cognizable' came back as কগনাইজেবল
    rather than আমলযোগ্য, which is the term used in Bangladeshi courts."""
    provider = RecordingProvider()

    await translate("A cognizable offence.", target="bn", provider=provider)

    system = provider.messages[0].content
    assert "আমলযোগ্য" in system
    assert "জামিনযোগ্য" in system


async def test_english_target_does_not_carry_the_bangla_glossary():
    provider = RecordingProvider()

    await translate("কিছু লেখা", target="en", provider=provider)

    assert "আমলযোগ্য" not in provider.messages[0].content


async def test_section_numbers_are_required_to_stay_in_latin_digits():
    """Bengali numerals here would break the link between the prose and the
    citations shown beside it."""
    provider = RecordingProvider()

    await translate("See section 561A.", target="bn", provider=provider)

    assert "Latin digits" in provider.messages[0].content


async def test_an_unsupported_language_is_refused():
    with pytest.raises(UnsupportedLanguage):
        await translate("text", target="fr", provider=RecordingProvider())


async def test_empty_text_does_not_reach_the_provider():
    provider = RecordingProvider()

    assert await translate("   ", target="bn", provider=provider) == ""
    assert provider.messages == []


def test_every_supported_language_has_a_notice():
    """A machine translation of legal information must say so, in the language the
    reader is reading."""
    for target in ("bn", "en"):
        assert NOTICE[target].strip()
