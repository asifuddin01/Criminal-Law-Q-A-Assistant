"""Answer contract.

Every system under evaluation — the bare model, and each later retrieval stage —
returns this shape, so the metrics code never learns which stage produced an answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "s. 54", "section 265-I", "CrPC-497", "Section 4(1)(b)" -> the section number alone.
_SECTION_TOKEN = re.compile(
    r"(?:(?:crpc|cr\.?p\.?c\.?)[\s\-]*)?"
    r"(?:sections?|secs?\.?|s\.)?\s*"
    r"(\d+\s*-?\s*[A-Z]{0,3})",
    re.I,
)


def normalize_section_number(raw: str) -> str | None:
    """Reduce a cited reference to a bare section number, or None if unusable.

    Citations arrive in whatever form the model produced. Normalising here means a
    correct citation written unusually is not scored as a miss, which would flatter
    retrieval by making the baseline look worse than it is.
    """
    if not raw:
        return None
    # Drop any subsection/clause tail: 4(1)(b) cites section 4.
    head = raw.strip().split("(")[0]
    match = _SECTION_TOKEN.search(head)
    if not match:
        return None
    number = re.sub(r"\s+", "", match.group(1)).upper()
    if not number or not number[0].isdigit():
        return None
    # 265-I keeps its hyphen; 46 A collapses to 46A.
    return number


@dataclass(frozen=True, slots=True)
class Citation:
    section: str
    quote: str = ""

    @property
    def normalized(self) -> str | None:
        return normalize_section_number(self.section)


@dataclass(slots=True)
class Answer:
    """What a system under evaluation returns for one question."""

    text: str
    citations: list[Citation] = field(default_factory=list)
    refused: bool = False
    model: str = ""
    raw: str = ""
    error: str | None = None
    # Sections retrieval put in front of the model, in rank order. Recorded so that
    # a retrieval miss can be told apart from a model that ignored what it was given
    # — the two call for opposite fixes.
    retrieved_sections: list[str] = field(default_factory=list)
