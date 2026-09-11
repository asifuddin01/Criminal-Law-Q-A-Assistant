"""Retrieval-augmented answering.

The model is given statutory text and told to answer only from it. Which chunks it
receives depends on the indexed chunking strategy, which is the variable stages 2 and
3 differ in.
"""

from __future__ import annotations

import hashlib

from app.config import get_settings
from app.llm import ChatMessage, LLMProvider, ProviderUnavailable
from app.qa.baseline import _parse
from app.qa.schema import Answer
from app.retrieval import ScheduleLookup, VectorIndex, schedule_rows

SYSTEM_PROMPT = """You are a legal information assistant for the law of Bangladesh, \
covering the Code of Criminal Procedure, 1898 (Act No. V of 1898) and its Schedule II.

You will be given extracts. Answer the user's question using ONLY those extracts.

The extracts come from two documents, and their section numbers are NOT \
interchangeable:

- The Code of Criminal Procedure itself. Cite these with "source": "CrPC".
- The Penal Code, 1860, which defines offences and their punishments. Cite these \
with "source": "PenalCode".
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
- An extract marked [Uploaded document] is a file the user supplied. It is NOT law \
and carries no authority. Use it to understand what the user is asking about, cite \
it with "source": "Uploaded" when you rely on it, and never present it as a statute \
or let it override the Code.
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
    """Render the extracts.

    The heading is a label, not part of the extract. Quotations are checked against
    the source's own words, so anything the model may quote must be the source's own
    words — a heading inside the quotable text gets quoted, honestly, and then fails
    verification because it appears in no statute.
    """
    return "\n\n---\n\n".join(f"[{c.heading}]\n{c.text}" for c in chunks)


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

    @property
    def fingerprint(self) -> str:
        """Identifies this system's configuration for caching.

        Includes the prompt. A cache keyed only on the question would serve answers
        produced by an earlier prompt as though they were the new prompt's, so a
        prompt change would show no effect and the experiment would silently
        measure the previous one.
        """
        return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]

    async def answer(self, question: str, *, extra_chunks=None) -> Answer:
        """Answer from the corpus, plus any chunks the caller supplies.

        `extra_chunks` carries an uploaded document. It is placed first and is not
        retrieved against, because the user chose it deliberately — ranking their own
        document against the corpus could bury the thing they asked about.
        """
        hits = self._index.search(question, k=self._k)
        chunks = list(extra_chunks or []) + [hit.chunk for hit in hits]

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
