"""Scoring tests.

The metrics are the instrument. A bug here does not produce a visible failure — it
produces a number that is wrong in a direction nobody checks.
"""

from __future__ import annotations

from app.evaluation.dataset import GoldQuestion
from app.evaluation.metrics import QuestionScore, aggregate, score_question
from app.ingest.models import Act, ScheduleEntry, Section, SectionUnit
from app.ingest.models import Triable as Tri
from app.qa.schema import CRPC, Answer, Citation


def _score(**kwargs) -> QuestionScore:
    base = dict(
        question_id="q-0001", slice="direct_lookup", answerable=True, refused=False
    )
    return QuestionScore(**{**base, **kwargs})


def test_errored_question_is_not_scored_as_a_correct_decision():
    """Regression. An errored answer has refused=False, so on an answerable
    question `refused != answerable` is true and 40 rate-limit failures were
    scored as correct refusal decisions, inflating refusal accuracy to 83%."""
    errored = _score(error="groq: Error code: 429")

    assert errored.measured is False
    assert errored.decided_correctly is False


def test_errors_are_excluded_from_rates_not_folded_into_them():
    scores = [
        _score(question_id="q-1", refused=False),  # answerable, answered: correct
        _score(question_id="q-2", error="429"),  # no measurement
        _score(question_id="q-3", error="429"),  # no measurement
    ]

    summary = aggregate(scores)

    assert summary["questions"] == 3
    assert summary["measured"] == 1
    assert summary["errors"] == 2
    # One measured question, decided correctly: 100%, not 33% and not 100% of three.
    assert summary["refusal_accuracy"] == 1.0


def test_refusal_is_correct_only_when_the_question_is_unanswerable():
    assert _score(answerable=False, refused=True).decided_correctly is True
    assert _score(answerable=False, refused=False).decided_correctly is False
    assert _score(answerable=True, refused=True).decided_correctly is False
    assert _score(answerable=True, refused=False).decided_correctly is True


def test_slice_breakdown_reports_errors_separately():
    scores = [
        _score(question_id="q-1", slice="direct_lookup"),
        _score(question_id="q-2", slice="direct_lookup", error="429"),
    ]

    bucket = aggregate(scores)["by_slice"]["direct_lookup"]

    assert bucket["n"] == 2
    assert bucket["errors"] == 1
    assert bucket["measured"] == 1
    assert bucket["refusal_accuracy"] == 1.0


def test_citation_existence_and_precision_are_independent():
    """The baseline cites real sections that are the wrong ones, so existence can
    be perfect while precision is zero. Both metrics are needed."""
    scores = [_score(citations_made=4, citations_existing=4, citations_correct=0)]

    summary = aggregate(scores)

    assert summary["citation_existence"] == 1.0
    assert summary["hallucinated_citation_rate"] == 0.0
    assert summary["citation_precision"] == 0.0


def test_rates_are_none_rather_than_zero_when_nothing_was_measured():
    summary = aggregate([_score(error="429")])

    assert summary["citation_existence"] is None
    assert summary["refusal_accuracy"] is None


# --- which document a citation is scored against ----------------------------


def _act(code_number: str, text: str, note: str = "") -> Act:
    return Act(
        act_id=75,
        title="test",
        act_number="V of 1898",
        source_url="x",
        fetched_at="2026-01-01T00:00:00Z",
        source_hash="0" * 64,
        sections=[
            Section(
                number=code_number,
                units=[SectionUnit(marginal_note=note, text=text)],
            )
        ],
    )


def _entry(section: str, offence: str) -> ScheduleEntry:
    return ScheduleEntry(
        penal_code_section=section,
        offence=offence,
        cognizable=Tri.YES,
        warrant_or_summons="Warrant",
        bailable=Tri.NO,
        compoundable=Tri.NO,
        punishment="Imprisonment",
        triable_by="Court of Session",
        chapter="XVII",
        page=1,
    )


def _question() -> GoldQuestion:
    return GoldQuestion(
        id="q-0001",
        question="Is theft bailable?",
        language="en",
        slice="direct_lookup",
        gold_sections=["ScheduleII-379"],
        answerable=True,
        verified_against="Schedule II, row for Penal Code section 379",
    )


def test_schedule_citation_is_scored_against_schedule_not_the_code():
    """Regression. Section numbers repeat across documents.

    Scoring resolved every citation against the Code, so a Schedule II quotation
    about theft was compared to Code of Criminal Procedure section 379 — a
    different provision that merely shares a number. The quotation was faithful and
    was counted as unsupported, on exactly the offence questions stage 4 exists to
    answer.
    """
    code = _act("379", "379. An appeal shall lie to the High Court Division.")
    schedule = [_entry("379", "Theft")]
    answer = Answer(
        text="Theft is not bailable.",
        citations=[
            Citation(
                section="379",
                source="Schedule II",
                quote="This offence is not bailable.",
            )
        ],
        retrieved_sections=["ScheduleII:379"],
    )

    score = score_question(_question(), answer, {CRPC: code}, schedule=schedule)

    assert score.quotes_checked == 1
    assert score.quotes_valid == 1
    assert score.unsupported_quotes == []


def test_citation_into_an_uningested_document_is_not_resolved_against_the_code():
    code = _act("300", "300. A person once convicted may not be tried again.")
    answer = Answer(
        text="Murder is defined in Penal Code section 300.",
        citations=[
            Citation(
                section="300",
                source="PenalCode",
                quote="A person once convicted may not be tried again.",
            )
        ],
        retrieved_sections=["PenalCode:300"],
    )

    score = score_question(_question(), answer, {CRPC: code})

    # The Penal Code is not loaded, so the citation resolves to nothing. It must
    # not borrow the Code's section 300 and be confirmed against it.
    assert score.citations_existing == 0
    assert score.hallucinated_sections == ["300"]


def test_a_quotation_repaired_by_trimming_a_label_is_counted_separately():
    code = _act(
        "54",
        "54. (1) Any police-officer may, without an order from a Magistrate, arrest.",
        note="When police may arrest without warrant",
    )
    answer = Answer(
        text="...",
        citations=[
            Citation(
                section="54",
                source="CrPC",
                quote=(
                    "Section 54. When police may arrest without warrant (1) Any "
                    "police-officer may, without an order from a Magistrate, arrest."
                ),
            )
        ],
        retrieved_sections=["CrPC:54"],
    )

    score = score_question(_question(), answer, {CRPC: code})
    summary = aggregate([score])

    assert score.quotes_valid == 1
    assert score.quotes_repaired == 1
    assert summary["excerpt_validity"] == 1.0
    # Reported alongside, so the allowance is visible rather than absorbed.
    assert summary["excerpt_validity_unrepaired"] == 0.0


def test_real_text_under_the_wrong_section_is_not_scored_as_fabrication():
    """The two failures have opposite fixes.

    A chunk that crosses a section boundary contains another section's words. A
    model quoting it honestly produces real statutory text attributed to the wrong
    section — a chunking failure that no prompt removes. Counting it as
    fabrication says the model invented law, and points the fix at the model.
    """
    code = Act(
        act_id=75,
        title="test",
        source_url="x",
        fetched_at="2026-01-01T00:00:00Z",
        source_hash="0" * 64,
        sections=[
            Section(
                number="52",
                units=[
                    SectionUnit(
                        marginal_note="Search of women",
                        text="52. Whenever a woman is to be searched.",
                    )
                ],
            ),
            Section(
                number="53",
                units=[
                    SectionUnit(
                        marginal_note="Seizure of offensive weapons",
                        text=(
                            "53. The officer making any arrest may take from the "
                            "person arrested any offensive weapons."
                        ),
                    )
                ],
            ),
        ],
    )
    answer = Answer(
        text="...",
        citations=[
            Citation(
                section="52",
                source=CRPC,
                # Section 53's words, cited as 52 — what a window starting in 52
                # and running into 53 puts in front of the model.
                quote="The officer making any arrest may take from the person arrested",
            ),
            Citation(
                section="53",
                source=CRPC,
                quote="The officer shall immediately release the person on bail.",
            ),
        ],
        retrieved_sections=["CrPC:52", "CrPC:53"],
    )

    score = score_question(_question(), answer, {CRPC: code})

    assert score.quotes_checked == 2
    assert score.quotes_valid == 0
    assert score.quotes_misattributed == 1
    assert score.quotes_fabricated == 1
    assert score.misattributed_to == ["CrPC:52->CrPC:53"]

    summary = aggregate([score])
    assert summary["misattribution_rate"] == 0.5
    assert summary["fabrication_rate"] == 0.5


def test_a_faithful_but_overelided_quotation_is_not_scored_as_fabrication():
    """Every word is the section's, in its order; one piece is too short to count.

    Rejected, correctly. But the scorer used to look the whole string up — ellipsis
    and all — in every section, find it nowhere, and call it invented law. On the
    hosted model at stage 4 that was ten of the eighteen "fabrications".
    """
    code = _act(
        "494",
        (
            "494. Any Public Prosecutor may, with the consent of the Court, at any "
            "time before the judgment is pronounced, withdraw from the prosecution "
            "of any person; and upon such withdrawal, if it is made after a charge "
            "has been framed, he shall be acquitted in respect of such offence."
        ),
        note="Effect of withdrawal from prosecution",
    )
    answer = Answer(
        text="...",
        citations=[
            Citation(
                section="494",
                source="CrPC",
                # The verbatim opening is kept short, so the prefix allowance cannot
                # show it on its own and the quotation stays rejected — which is the
                # case being scored.
                quote=(
                    "Any Public Prosecutor ... shall ... be acquitted in respect of "
                    "such offence"
                ),
            )
        ],
        retrieved_sections=["CrPC:494"],
    )

    score = score_question(_question(), answer, {CRPC: code})
    summary = aggregate([score])

    assert score.quotes_checked == 1
    assert score.quotes_valid == 0
    assert score.quotes_overelided == 1
    assert score.quotes_fabricated == 0
    # Every checked quotation lands in exactly one place.
    assert (
        summary["excerpt_validity"]
        + summary["misattribution_rate"]
        + summary["fabrication_rate"]
        + summary["overelision_rate"]
        + summary["recomposition_rate"]
    ) == 1.0
