"""Stage 1: the bare model, with no retrieval.

This exists to establish the floor. A retrieval system that cannot beat an
unassisted model on citation accuracy is not earning its complexity, and without
this measurement that claim cannot be made in either direction.

The model is asked to answer and cite exactly as the finished system would, so the
comparison is like for like. It is given no statutory text, so every section number
it produces comes from its own weights.
"""

from __future__ import annotations

import hashlib
import json
import re

from app.config import get_settings
from app.llm import ChatMessage, LLMProvider, ProviderUnavailable
from app.qa.schema import Answer, Citation

SYSTEM_PROMPT = """You are a legal information assistant for the law of Bangladesh, \
covering the Code of Criminal Procedure, 1898 (Act No. V of 1898).

Answer the user's question about Bangladeshi criminal procedure. Ground every \
statement in specific provisions and cite them.

If the question cannot be answered from the Code of Criminal Procedure — because it \
concerns substantive offences, evidence law, another statute, case law, or a \
non-legal matter — say so instead of answering. If the question is too vague to \
answer without knowing which offence or proceeding is meant, say what you would need \
to know instead of guessing.

Reply with JSON only, in exactly this shape:

{
  "refused": false,
  "answer": "your answer in plain English",
  "citations": [
    {"section": "54", "quote": "exact words from that section"}
  ]
}

Set "refused" to true when you cannot or should not answer, leave "citations" empty, \
and put your reason in "answer". Quote only text you are certain appears in the \
section. Cite section numbers alone, such as "54", "497" or "561A"."""

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _parse(raw: str) -> tuple[str, list[Citation], bool]:
    """Extract the answer from the model's reply.

    Parsed leniently on purpose: a malformed reply is a property of the model under
    test, and discarding it as an error would quietly remove the worst-behaved cases
    from the baseline and flatter it.
    """
    match = _JSON_BLOCK.search(raw)
    if not match:
        return raw.strip(), [], False

    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return raw.strip(), [], False

    if not isinstance(payload, dict):
        return raw.strip(), [], False

    citations: list[Citation] = []
    for item in payload.get("citations") or []:
        if isinstance(item, dict):
            section = str(item.get("section", "")).strip()
            if section:
                citations.append(
                    Citation(
                        section=section,
                        quote=str(item.get("quote", "")).strip(),
                        source=str(item.get("source") or "CrPC").strip() or "CrPC",
                    )
                )
        elif isinstance(item, str) and item.strip():
            citations.append(Citation(section=item.strip()))

    return (
        str(payload.get("answer", "")).strip(),
        citations,
        bool(payload.get("refused", False)),
    )


class BaselineLLM:
    """Answers from model weights alone. No corpus, no retrieval."""

    name = "baseline-llm-only"

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    @property
    def fingerprint(self) -> str:
        """Identifies this system's configuration for caching.

        Includes the prompt. A cache keyed only on the question would serve answers
        produced by an earlier prompt as though they were the new prompt's, so a
        prompt change would show no effect and the experiment would silently
        measure the previous one.
        """
        return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]

    async def answer(self, question: str) -> Answer:
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=question),
        ]
        try:
            completion = await self._provider.complete(
                messages, max_tokens=get_settings().answer_max_tokens
            )
        except ProviderUnavailable as exc:
            return Answer(text="", error=str(exc))

        if not completion.text.strip():
            # Recorded as an error rather than an answer with no citations. Scoring
            # an empty completion as "cited nothing" would understate the baseline's
            # citation behaviour and hide a truncation bug as a model result.
            return Answer(
                text="",
                model=completion.model,
                error="empty completion (likely truncated before content)",
            )

        text, citations, refused = _parse(completion.text)
        return Answer(
            text=text,
            citations=citations,
            refused=refused,
            model=completion.model,
            raw=completion.text,
        )
