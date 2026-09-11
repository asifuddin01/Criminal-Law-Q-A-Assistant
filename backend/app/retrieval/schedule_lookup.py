"""Direct lookup of offences in Schedule II.

Dense retrieval fails on offence classification, and fails in a way that looks like
success. "Is theft a bailable offence?" embeds close to the sections *about* bail —
496 and 497 — because those are the passages in the corpus most about bail. The row
that actually answers it, Penal Code section 379, ranks nowhere: it is a short entry
whose salient word is "theft", and the question's remaining words all point
elsewhere.

Retrieval would then hand the model the general bail provisions and the model would
answer from them, fluently and with real citations, without ever seeing the table
that decides the question.

So offences are looked up by name rather than by embedding. A question naming an
offence gets that offence's row placed in front of the model directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingest.models import ScheduleEntry

# "section 302 of the Penal Code", "Penal Code s. 420", "u/s 379 PC"
PENAL_SECTION = re.compile(
    r"(?:penal\s+code[^.]{0,20}?|u/?s\.?\s*)(\d{1,3}[A-Z]{0,3})"
    r"|(\d{1,3}[A-Z]{0,3})\s*(?:of\s+the\s+)?penal\s+code",
    re.I,
)

# Words too common to identify an offence on their own.
STOPWORDS = frozenset(
    # fmt: off
    {
        "a", "an", "the", "of", "or", "and", "to", "in", "for", "by", "with",
        "any", "other", "such", "person", "persons", "property", "offence",
        "offences", "act", "if", "when", "where", "which", "whoever", "thereby",
        "being", "made", "not", "under", "upon", "his", "her", "their", "its",
        "on", "at", "from", "into", "as", "is", "are", "be", "may", "shall",
    }
    # fmt: on
)

MIN_PHRASE = 4


@dataclass(frozen=True, slots=True)
class Match:
    entry: ScheduleEntry
    phrase: str
    reason: str


def _headword(offence: str) -> str:
    """The offence's name, before any qualifying clause.

    Rows read "Theft", but also "Theft in a dwelling house, etc." and "Robbery If
    committed on the highway...". The leading phrase is what a question names.
    """
    head = re.split(r"[.,;]| if | when | where ", offence, maxsplit=1, flags=re.I)[0]
    return " ".join(head.lower().split())


def _significant(phrase: str) -> bool:
    words = [w for w in re.findall(r"[a-z]+", phrase) if w not in STOPWORDS]
    return bool(words) and len(phrase) >= MIN_PHRASE


class ScheduleLookup:
    """Finds the Schedule II rows a question is asking about."""

    def __init__(self, entries: list[ScheduleEntry]) -> None:
        self.entries = entries
        self._by_section: dict[str, list[ScheduleEntry]] = {}
        self._by_phrase: dict[str, list[ScheduleEntry]] = {}

        for entry in entries:
            self._by_section.setdefault(entry.penal_code_section.upper(), []).append(
                entry
            )
            phrase = _headword(entry.offence)
            if _significant(phrase):
                self._by_phrase.setdefault(phrase, []).append(entry)

        # Longest first, so "criminal breach of trust" wins over "criminal breach".
        self._phrases = sorted(self._by_phrase, key=len, reverse=True)

    def find(self, question: str, *, limit: int = 4) -> list[Match]:
        text = " ".join(question.lower().split())
        matches: list[Match] = []
        seen: set[int] = set()

        for raw, trailing in PENAL_SECTION.findall(question):
            number = (raw or trailing).upper()
            for entry in self._by_section.get(number, []):
                if id(entry) not in seen:
                    seen.add(id(entry))
                    matches.append(
                        Match(entry, number, f"question names Penal Code section {number}")
                    )

        for phrase in self._phrases:
            if len(matches) >= limit:
                break
            if not re.search(rf"\b{re.escape(phrase)}\b", text):
                continue
            for entry in self._by_phrase[phrase]:
                if id(entry) not in seen:
                    seen.add(id(entry))
                    matches.append(
                        Match(entry, phrase, f"question names the offence {phrase!r}")
                    )

        return matches[:limit]
