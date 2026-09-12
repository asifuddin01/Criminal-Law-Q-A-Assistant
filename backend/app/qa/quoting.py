"""Does this quotation appear in this section?

One implementation, used by both the validation gate and the evaluation metrics.
They had separate copies, and they drifted: the gate learned to resolve a citation
against the document it claims while the scorer went on checking every citation
against the Code, so a Schedule II quotation was compared to whichever Code section
shared its number. Both now call this.

The comparison is a substring test, deliberately. No model is asked whether the
model was honest. What the test has to get right is *what counts as the section's
own words*, and there are three ways a faithful quotation fails a naive one:

  - bdlaws marks amended words with square brackets and words repealed out of a
    provision with ``[* * *]``. Those are editorial apparatus recording how the
    section reached its current form; they are not enacted words, and no one
    quoting the law reproduces them.
  - a quotation that elides a passage with an ellipsis is ordinary legal practice.
  - a model handed a labelled extract will sometimes copy the label into the
    quotation along with the text.

None of the three is a fabrication, and each was being counted as one. They are
handled by canonicalising both sides, by checking elided segments in order, and by
trimming a leading label — never by relaxing the requirement that the remaining
words appear, verbatim and contiguously, in the section cited.

Every repair is named in the result, so the count of quotations that needed one is
reportable rather than hidden inside a pass rate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Below this length a quotation matches too easily to be evidence of anything.
MIN_QUOTE_CHARS = 20

# "[* * *]" and "[***]": words the legislature removed. Dropped rather than
# stripped to bare asterisks, so the surrounding words close up as they read.
_ELIDED_BY_AMENDMENT = re.compile(r"\[\s*(?:\*\s*)+\]")

# An ellipsis in a quotation marks the author's own omission.
_ELLIPSIS = re.compile(r"\s*(?:\.\s*\.\s*\.|…)\s*")

# "54.", "Section 265-I —", "46A:" at the head of a quotation.
_LEADING_LABEL = re.compile(r"^\s*(?:section\s+)?\d+\s*-?\s*[A-Za-z]{0,3}\s*[.\-—:]\s*", re.I)


# A space in front of punctuation, which a quotation never carries. Ingestion now
# closes these up at the source (they were footnote markers), but a quotation is
# compared against whatever the corpus holds, and a corpus is re-fetched.
_SPACED_PUNCTUATION = re.compile(r"\s+([,.;:)\]])")


def canonical(text: str) -> str:
    """The section's own words, case- and whitespace-insensitive.

    Applied to both sides of every comparison, so it can never admit text that is
    not in the source — only text that differs from it in apparatus the source
    carries and a quotation would not.
    """
    text = _ELIDED_BY_AMENDMENT.sub(" ", text)
    text = text.replace("[", " ").replace("]", " ")
    text = " ".join(text.split()).lower()
    return _SPACED_PUNCTUATION.sub(r"\1", text)


@dataclass(frozen=True, slots=True)
class QuoteCheck:
    """The outcome of checking one quotation against one section."""

    verified: bool
    # What to show the user: the quotation, trimmed of a label it should not have
    # carried. Empty when nothing could be verified — a quotation that cannot be
    # substantiated is worse than no quotation, so it is not displayed.
    quote: str
    # Which allowance, if any, the quotation needed. "" when it matched outright.
    repair: str = ""

    @property
    def repaired(self) -> bool:
        return self.verified and bool(self.repair)


def _contains_in_order(haystack: str, segments: list[str]) -> bool:
    """Every segment appears, in the order given, without overlapping."""
    cursor = 0
    for segment in segments:
        found = haystack.find(segment, cursor)
        if found < 0:
            return False
        cursor = found + len(segment)
    return True


def _too_short(text: str) -> bool:
    return len(canonical(text)) < MIN_QUOTE_CHARS


def check_quote(quote: str, body: str, *, marginal_note: str = "") -> QuoteCheck:
    """Check a quotation against the text of the section it is attributed to.

    `marginal_note` is the section's heading. It is passed so it can be *trimmed*
    from the front of a quotation, never so it can be matched: a marginal note is
    not enacted text, and a "quotation" consisting only of one is a label presented
    as law. That case verifies nothing and returns an empty quote.
    """
    quote = quote.strip()
    if _too_short(quote):
        return QuoteCheck(verified=False, quote="")

    target = canonical(body)
    if not target:
        return QuoteCheck(verified=False, quote="")

    for candidate, repair in _candidates(quote, marginal_note):
        if _too_short(candidate):
            continue
        segments = [s for s in _ELLIPSIS.split(candidate) if canonical(s)]
        if len(segments) > 1:
            parts = [canonical(s) for s in segments]
            if any(len(p) < MIN_QUOTE_CHARS for p in parts):
                # An elision leaving fragments this small stops being a quotation.
                continue
            if _contains_in_order(target, parts):
                joined = "elision" if not repair else f"{repair}+elision"
                return QuoteCheck(True, candidate.strip(), joined)
            continue
        if canonical(candidate) in target:
            return QuoteCheck(True, candidate.strip(), repair)

    return QuoteCheck(verified=False, quote="")


def _candidates(quote: str, marginal_note: str):
    """The quotation, then the same text with a citation label trimmed off.

    Order matters: a quotation that matches as written is never reported as
    repaired, so the repair count means what it says.
    """
    yield quote, ""

    trimmed = quote
    note = marginal_note.strip().rstrip(".")
    for _ in range(2):  # "54. Arrest how made" is a number *and* a note.
        stripped = _LEADING_LABEL.sub("", trimmed, count=1)
        if note and canonical(stripped).startswith(canonical(note)):
            cut = len(canonical(note))
            # Walk the original forward past however much of it the note occupied.
            stripped = _drop_leading(stripped, cut)
        if stripped == trimmed:
            break
        trimmed = stripped.lstrip(" .:-—\n")

    if trimmed != quote and trimmed:
        yield trimmed, "label"


def _drop_leading(text: str, canonical_chars: int) -> str:
    """Drop the prefix of `text` whose canonical form is `canonical_chars` long."""
    seen = 0
    for index, _ in enumerate(text):
        if seen >= canonical_chars:
            return text[index:]
        seen = len(canonical(text[: index + 1]))
    return ""


class SourceIndex:
    """Every section's text, for asking where a quotation actually came from.

    A quotation that fails against the section it cites has failed in one of two
    ways, and they are not the same failure. Either the text exists nowhere in the
    corpus — the model wrote it — or it is real statutory text attributed to the
    wrong section, which is what a chunk crossing a section boundary produces when
    the model quotes it honestly.

    They call for opposite fixes. Fabrication is a model and prompt problem;
    misattribution is a chunking problem, and no amount of prompting removes it if
    the chunk the model was shown genuinely contains another section's words.
    Reporting them as one number hides which one a stage is suffering from.
    """

    __slots__ = ("_bodies",)

    def __init__(self, bodies) -> None:
        # (identifier, canonical text), built once and searched linearly. The
        # corpus is a few thousand sections and this runs only for quotations that
        # already failed, so the scan costs less than the indexing would.
        self._bodies = [(name, canonical(text)) for name, text in bodies if text]

    def locate(self, quote: str) -> str | None:
        """The section this text really belongs to, or None if it belongs to none."""
        needle = canonical(quote)
        if len(needle) < MIN_QUOTE_CHARS:
            return None
        for name, body in self._bodies:
            if needle in body:
                return name
        return None
