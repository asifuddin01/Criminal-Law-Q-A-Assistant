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
from app.retrieval import SCHEDULE_II, ScheduleLookup, VectorIndex, schedule_rows

SYSTEM_PROMPT = """You are a legal information assistant for the law of Bangladesh, \
covering the Code of Criminal Procedure, 1898 (Act No. V of 1898) and its Schedule II.

You will be given extracts. Answer the user's question using ONLY those extracts.

The extracts come from two documents, and their section numbers are NOT \
interchangeable:

- The Code of Criminal Procedure itself. Cite these with "source": "CrPC".
- Schedule II, a table classifying offences under the Penal Code — whether each is \
cognizable, bailable, compoundable, and which court tries it. Cite these with \
"source": "Schedule II", and give the Penal Code section number. Penal Code section \
379 is theft; Code of Criminal Procedure section 379 is something else entirely.

Rules:
- Cite only sections that appear in the extracts below. Never cite one you were not \
given.
- Whether an offence is bailable or cognizable is answered by Schedule II, not by \
the definitions in section 4. Section 4 only says where to look.
- Where Schedule II says an attribute depends on another offence, say that it \
depends. Do not resolve it yourself.
- Quote only text that appears verbatim in the extracts. Copy it exactly.
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
    {"section": "54", "source": "CrPC", "quote": "exact words from the extract"},
    {"section": "379", "source": "Schedule II", "quote": "exact words"}
  ]
}

Set "refused" to true when the extracts do not support an answer, leave "citations" \
empty, and put your reason in "answer"."""


def _format_context(chunks) -> str:
    blocks = []
    for chunk in chunks:
        if chunk.document == SCHEDULE_II:
            heading = f"[Schedule II — Penal Code section {chunk.section_number}]"
        else:
            heading = f"[CrPC Section {chunk.section_number}]"
        if chunk.marginal_note:
            heading += f" {chunk.marginal_note}"
        blocks.append(f"{heading}\n{chunk.text}")
    return "\n\n---\n\n".join(blocks)


class RetrievalQA:
    """Stage 2 onward: answer from retrieved statutory text."""

    def __init__(
        self,
        provider: LLMProvider,
        index: VectorIndex,
        *,
        name: str,
        k: int = 8,
        lookup: ScheduleLookup | None = None,
    ) -> None:
        self._provider = provider
        self._index = index
        self._k = k
        self._lookup = lookup
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
        chunks = [hit.chunk for hit in hits]

        # A question naming an offence is answered by Schedule II, and embedding
        # will not find it: "is theft bailable" sits closest to the sections *about*
        # bail, not to the one-line row that decides it. Those rows are placed in
        # front of the model directly, ahead of whatever retrieval returned.
        if self._lookup is not None:
            matched = schedule_rows([m.entry for m in self._lookup.find(question)])
            known = {(c.document, c.section_number) for c in chunks}
            chunks = [
                c for c in matched if (c.document, c.section_number) not in known
            ] + chunks

        retrieved = list(dict.fromkeys(c.identifier for c in chunks))

        if not chunks:
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
                    f"Extracts:\n\n{_format_context(chunks)}\n\n"
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
