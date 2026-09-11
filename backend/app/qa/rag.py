"""Retrieval-augmented answering.

The model is given statutory text and told to answer only from it. Which chunks it
receives depends on the indexed chunking strategy, which is the variable stages 2 and
3 differ in.
"""

from __future__ import annotations

from app.config import get_settings
from app.llm import ChatMessage, LLMProvider, ProviderUnavailable
from app.qa.baseline import _parse
from app.qa.schema import Answer
from app.retrieval import VectorIndex

SYSTEM_PROMPT = """You are a legal information assistant for the law of Bangladesh, \
covering the Code of Criminal Procedure, 1898 (Act No. V of 1898).

You will be given extracts from the Code. Answer the user's question using ONLY those \
extracts.

Rules:
- Cite only section numbers that appear in the extracts below. Never cite a section \
you were not given.
- Quote only text that appears verbatim in the extracts. Copy it exactly; do not \
paraphrase inside a quote.
- If the extracts do not answer the question, say so and refuse. Do not fall back on \
what you remember about criminal procedure in other countries — the Bangladesh Code \
numbers its provisions differently.
- If the question is too vague to answer without knowing which offence or proceeding \
is meant, say what you would need to know instead of guessing.

Reply with JSON only, in exactly this shape:

{
  "refused": false,
  "answer": "your answer in plain English",
  "citations": [
    {"section": "54", "quote": "exact words copied from the extract"}
  ]
}

Set "refused" to true when the extracts do not support an answer, leave "citations" \
empty, and put your reason in "answer"."""


def _format_context(hits) -> str:
    blocks = []
    for hit in hits:
        chunk = hit.chunk
        heading = f"[Section {chunk.section_number}]"
        if chunk.marginal_note:
            heading += f" {chunk.marginal_note}"
        blocks.append(f"{heading}\n{chunk.text}")
    return "\n\n---\n\n".join(blocks)


class RetrievalQA:
    """Stage 2 onward: answer from retrieved statutory text."""

    def __init__(
        self, provider: LLMProvider, index: VectorIndex, *, name: str, k: int = 8
    ) -> None:
        self._provider = provider
        self._index = index
        self._k = k
        self.name = name

    @property
    def model_name(self) -> str:
        """The chat model answering, for cache keys and reporting."""
        return getattr(self._provider, "_chat_model", self._provider.name)

    @property
    def index_name(self) -> str:
        """The embedding model the index was built with.

        Part of the cache key: an answer cached under one index must never be served
        after the index changes, or the system would be reporting text it no longer
        retrieves.
        """
        return self._index.model_name

    async def answer(self, question: str) -> Answer:
        hits = self._index.search(question, k=self._k)
        retrieved = list(dict.fromkeys(h.chunk.section_number for h in hits))

        if not hits:
            return Answer(
                text="No statutory text was retrieved for this question.",
                refused=True,
                retrieved_sections=retrieved,
            )

        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=(
                    f"Extracts from the Code:\n\n{_format_context(hits)}\n\n"
                    f"Question: {question}"
                ),
            ),
        ]
        try:
            completion = await self._provider.complete(
                messages, max_tokens=get_settings().answer_max_tokens
            )
        except ProviderUnavailable as exc:
            return Answer(text="", error=str(exc), retrieved_sections=retrieved)

        if not completion.text.strip():
            return Answer(
                text="",
                model=completion.model,
                error="empty completion (likely truncated before content)",
                retrieved_sections=retrieved,
            )

        text, citations, refused = _parse(completion.text)
        return Answer(
            text=text,
            citations=citations,
            refused=refused,
            model=completion.model,
            raw=completion.text,
            retrieved_sections=retrieved,
        )
