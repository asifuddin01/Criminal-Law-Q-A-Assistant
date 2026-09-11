"""Scoring.

Three of these are deterministic and need no judge: whether a cited section exists,
whether it is the right one, and whether a quoted excerpt actually appears in the
section it is attributed to. Those three are enough to measure the failure this
system exists to prevent — confident citation of text that does not say what the
answer claims, or does not exist at all.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from app.evaluation.dataset import GoldQuestion
from app.qa.schema import Answer

# Quotes shorter than this match too easily to be evidence of anything.
MIN_QUOTE_CHARS = 20


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass(slots=True)
class QuestionScore:
    question_id: str
    slice: str
    answerable: bool
    refused: bool
    error: str | None = None

    citations_made: int = 0
    citations_existing: int = 0
    citations_correct: int = 0

    quotes_checked: int = 0
    quotes_valid: int = 0

    retrieved: int = 0
    retrieval_hit: bool = False

    hallucinated_sections: list[str] = field(default_factory=list)
    unsupported_quotes: list[str] = field(default_factory=list)

    @property
    def measured(self) -> bool:
        """Whether this question produced an answer that can be scored at all.

        A question whose request failed has no measurement. It must not fall
        through into the rates: an errored answer has refused=False, so on an
        answerable question `refused != answerable` is true and the failure would
        score as a correct decision.
        """
        return self.error is None

    @property
    def decided_correctly(self) -> bool:
        """Refusal is correct exactly when the question is unanswerable."""
        return self.measured and (self.refused != self.answerable)

    @property
    def has_correct_citation(self) -> bool:
        return self.citations_correct > 0


def score_question(question: GoldQuestion, answer: Answer, corpus) -> QuestionScore:
    """Score one answer against its gold entry and the parsed corpus."""
    score = QuestionScore(
        question_id=question.id,
        slice=question.slice.value,
        answerable=question.answerable,
        refused=answer.refused,
        error=answer.error,
    )
    if answer.error:
        return score

    # Gold labels are qualified by document ("CrPC-54"), and so are retrieved
    # sections ("CrPC:54"), because a bare number is ambiguous between the Code and
    # Schedule II. Bare numbers are also accepted: answers cached before the
    # qualified form existed store them, and re-running from cache should resume
    # rather than silently score zero recall against its own history.
    gold = {f"{code}:{number}" for code, number in question.targets}
    gold_numbers = {number for _, number in question.targets}

    score.retrieved = len(answer.retrieved_sections)
    if gold:
        retrieved = set(answer.retrieved_sections)
        score.retrieval_hit = bool(
            (gold & retrieved) or (gold_numbers & retrieved)
        )

    for citation in answer.citations:
        number = citation.normalized
        score.citations_made += 1
        if number is None:
            score.hallucinated_sections.append(citation.section)
            continue

        section = corpus.section(number)
        if section is None:
            score.hallucinated_sections.append(number)
            continue

        score.citations_existing += 1
        if f"{citation.document}:{number}" in gold or number in gold_numbers:
            score.citations_correct += 1

        quote = _normalize(citation.quote)
        if len(quote) >= MIN_QUOTE_CHARS:
            score.quotes_checked += 1
            if quote in _normalize(section.text):
                score.quotes_valid += 1
            else:
                score.unsupported_quotes.append(citation.quote[:120])

    return score


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def aggregate(scores: list[QuestionScore]) -> dict:
    """Roll individual scores into the metrics reported per stage."""
    errored = [s for s in scores if not s.measured]
    measured = [s for s in scores if s.measured]

    # Every rate below is computed over measured questions only. Errors are
    # reported as a count, never folded into a rate as if they were an outcome.
    answerable = [s for s in measured if s.answerable]
    unanswerable = [s for s in measured if not s.answerable]

    cited = sum(s.citations_made for s in measured)
    existing = sum(s.citations_existing for s in measured)
    correct = sum(s.citations_correct for s in answerable)
    correct_denominator = sum(s.citations_made for s in answerable)
    quotes = sum(s.quotes_checked for s in measured)
    valid_quotes = sum(s.quotes_valid for s in measured)

    by_slice: dict[str, dict] = {}
    for score in scores:
        bucket = by_slice.setdefault(
            score.slice,
            {"n": 0, "errors": 0, "decided_correctly": 0, "with_correct_citation": 0},
        )
        bucket["n"] += 1
        if not score.measured:
            bucket["errors"] += 1
            continue
        bucket["decided_correctly"] += int(score.decided_correctly)
        bucket["with_correct_citation"] += int(score.has_correct_citation)
    for bucket in by_slice.values():
        bucket["measured"] = bucket["n"] - bucket["errors"]
        bucket["refusal_accuracy"] = _ratio(
            bucket["decided_correctly"], bucket["measured"]
        )

    return {
        "questions": len(scores),
        "measured": len(measured),
        "errors": len(errored),
        "citations_made": cited,
        # Of everything cited, how much refers to a section that exists at all.
        "citation_existence": _ratio(existing, cited),
        "hallucinated_citation_rate": (
            None if not cited else round(1 - existing / cited, 4)
        ),
        # Of citations on answerable questions, how much matches the gold label.
        "citation_precision": _ratio(correct, correct_denominator),
        "answer_hit_rate": _ratio(
            sum(1 for s in answerable if s.has_correct_citation), len(answerable)
        ),
        # Recall is defined over answerable questions only: an unanswerable
        # question has no gold section for retrieval to find.
        "retrieval_recall": _ratio(
            sum(1 for s in answerable if s.retrieval_hit), len(answerable)
        )
        if any(s.retrieved for s in measured)
        else None,
        "excerpt_validity": _ratio(valid_quotes, quotes),
        "quotes_checked": quotes,
        "refusal_accuracy": _ratio(
            sum(1 for s in measured if s.decided_correctly), len(measured)
        ),
        "refused_when_unanswerable": _ratio(
            sum(1 for s in unanswerable if s.refused), len(unanswerable)
        ),
        "refused_when_answerable": _ratio(
            sum(1 for s in answerable if s.refused), len(answerable)
        ),
        "by_slice": by_slice,
    }


def to_record(score: QuestionScore) -> dict:
    return asdict(score)
