"""Scoring.

Three of these are deterministic and need no judge: whether a cited section exists,
whether it is the right one, and whether a quoted excerpt actually appears in the
section it is attributed to. Those three are enough to measure the failure this
system exists to prevent — confident citation of text that does not say what the
answer claims, or does not exist at all.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.evaluation.dataset import GoldQuestion
from app.ingest.models import Act, ScheduleEntry
from app.qa.quoting import MIN_QUOTE_CHARS, SourceIndex, canonical, check_quote
from app.qa.schema import CRPC, SCHEDULE_II, Answer
from app.retrieval.chunking import schedule_rows


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
    # Of the invalid ones: real statutory text attributed to the wrong section,
    # against text that appears nowhere in the corpus. A chunk crossing a section
    # boundary produces the first when the model quotes it honestly; only the
    # second is the model inventing law.
    quotes_misattributed: int = 0
    quotes_fabricated: int = 0
    # Neither of those. The cited section's own words, in order, elided down to a
    # piece too short to be evidence; and real pieces of statute assembled into a
    # sentence the statute does not contain. Both are rejected. Neither is invented
    # text, and both were being counted as if they were.
    quotes_overelided: int = 0
    quotes_recomposed: int = 0

    retrieved: int = 0
    retrieval_hit: bool = False

    hallucinated_sections: list[str] = field(default_factory=list)
    unsupported_quotes: list[str] = field(default_factory=list)
    # "CrPC:52->CrPC:53": cited the first, quoted the second's words.
    misattributed_to: list[str] = field(default_factory=list)
    # Quotations that verified only after a label was trimmed or an elision read as
    # one. Counted separately so excerpt validity can be reported with and without
    # the allowance rather than quietly including it.
    quotes_repaired: int = 0

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


# Built once per corpus rather than per question: the index is a few thousand
# canonicalised strings, and rebuilding it 101 times would dominate scoring.
_SOURCE_CACHE: dict[tuple, SourceIndex] = {}


def _sources(acts: dict[str, Act], schedule_text: dict[str, str]) -> SourceIndex:
    key = tuple(sorted((code, a.act_id, len(a.sections)) for code, a in acts.items()))
    key += (len(schedule_text),)
    cached = _SOURCE_CACHE.get(key)
    if cached is None:
        bodies = [
            (f"{code}:{section.number}", section.text)
            for code, act in acts.items()
            for section in act.sections
        ]
        bodies += [(f"{SCHEDULE_II}:{n}", t) for n, t in schedule_text.items()]
        cached = SourceIndex(bodies)
        _SOURCE_CACHE[key] = cached
    return cached


def score_question(
    question: GoldQuestion,
    answer: Answer,
    corpora: Act | dict[str, Act],
    *,
    schedule: list[ScheduleEntry] | None = None,
) -> QuestionScore:
    """Score one answer against its gold entry and the parsed corpus.

    `corpora` maps a document code to the act it names; a bare Act is read as the
    Code, which is what it meant when there was only one. A citation is resolved
    against the document it claims. Scoring every citation against the Code — which
    this did — compared a Schedule II quotation to whichever Code section happened
    to share its number, and marked the offence questions stage 4 exists to answer
    as unsupported.
    """
    acts = corpora if isinstance(corpora, dict) else {CRPC: corpora}
    schedule_text = {c.section_number: c.text for c in schedule_rows(schedule or [])}
    schedule_notes = {
        e.penal_code_section: e.offence.strip().rstrip(".") for e in (schedule or [])
    }
    sources = _sources(acts, schedule_text)
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

        if citation.document == SCHEDULE_II:
            body = schedule_text.get(number, "")
            note = schedule_notes.get(number, "")
        else:
            act = acts.get(citation.document)
            section = act.section(number) if act is not None else None
            body = section.text if section is not None else ""
            note = ""
            if section is not None and section.marginal_notes:
                note = section.marginal_notes[0]
        if not body:
            score.hallucinated_sections.append(number)
            continue

        score.citations_existing += 1
        if f"{citation.document}:{number}" in gold or number in gold_numbers:
            score.citations_correct += 1

        if len(canonical(citation.quote)) >= MIN_QUOTE_CHARS:
            score.quotes_checked += 1
            checked = check_quote(citation.quote, body, marginal_note=note)
            if checked.verified:
                score.quotes_valid += 1
                score.quotes_repaired += int(bool(checked.repair))
            else:
                score.unsupported_quotes.append(citation.quote[:120])
                verdict = (
                    sources.explain(citation.quote, body) if sources else "fabricated"
                )
                if verdict.startswith("misattributed:"):
                    found = verdict.split(":", 1)[1]
                    score.quotes_misattributed += 1
                    score.misattributed_to.append(f"{citation.document}:{number}->{found}")
                elif verdict == "overelided":
                    score.quotes_overelided += 1
                elif verdict == "recomposed":
                    score.quotes_recomposed += 1
                else:
                    score.quotes_fabricated += 1

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
    repaired_quotes = sum(s.quotes_repaired for s in measured)
    misattributed = sum(s.quotes_misattributed for s in measured)
    fabricated = sum(s.quotes_fabricated for s in measured)
    overelided = sum(s.quotes_overelided for s in measured)
    recomposed = sum(s.quotes_recomposed for s in measured)

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
        # Excerpt validity counting only quotations that matched as written. The
        # gap between the two is the cost of the allowances, stated rather than
        # absorbed into a single rate.
        "excerpt_validity_unrepaired": _ratio(valid_quotes - repaired_quotes, quotes),
        # Of every quotation checked, the share that is real statutory text under
        # the wrong section, and the share that is not in the corpus at all. The
        # first is a chunking failure, the second the model inventing law.
        "misattribution_rate": _ratio(misattributed, quotes),
        "fabrication_rate": _ratio(fabricated, quotes),
        # The rest of the rejections, so the four shares and excerpt validity
        # account for every quotation checked.
        "overelision_rate": _ratio(overelided, quotes),
        "recomposition_rate": _ratio(recomposed, quotes),
        "quotes_checked": quotes,
        "quotes_repaired": repaired_quotes,
        "quotes_misattributed": misattributed,
        "quotes_fabricated": fabricated,
        "quotes_overelided": overelided,
        "quotes_recomposed": recomposed,
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
