"""Gold evaluation dataset: loading and validation.

A wrong gold label is the most damaging error available here. It penalises correct
retrieval and rewards incorrect retrieval, and it does so invisibly, because nothing
downstream can detect that the label was wrong. Labels are therefore validated
against the parsed corpus rather than trusted, and validation is a hard failure.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
GOLD_PATH = REPO_ROOT / "eval" / "dataset" / "gold.jsonl"

# Act codes used in gold_sections identifiers, mapped to bdlaws act ids where the
# act is fetchable. Entries with a None id are not single acts (Schedule II is a PDF).
ACT_CODES: dict[str, int | None] = {
    "CrPC": 75,
    "PenalCode": 11,
    "EvidenceAct": 24,
    "NariOShishu2000": None,
    "NarcoticsControlAct": None,
    "CrPC-Schedule-II": None,
    # Schedule II is a table of Penal Code offences, not an act. Written without a
    # space because gold labels split on the first hyphen and the code must survive
    # that intact.
    "ScheduleII": None,
}



# A distinctive phrase that must appear in each cited section's text.
#
# Resolution alone is a weak check: a label can point at a real section that is
# simply the wrong one. These phrases were taken from the section text at the time
# the questions were written, so they assert that the label still points at the
# provision the question was written against. They double as a corpus-drift
# detector — if bdlaws republishes a section in different words, this fails loudly
# rather than quietly degrading every metric computed from the label.
SECTION_EXPECTATIONS: dict[str, str] = {
    # Schedule II rows. The phrase asserts the row still describes the offence the
    # question was written about, not merely that the number resolves.
    "PenalCode-300": "murder",
    "PenalCode-379": "theft",
    "ScheduleII-302": "murder",
    "ScheduleII-379": "theft",
    "ScheduleII-406": "criminal breach of trust",
    "CrPC-46A": "memorandum of arrest",
    "CrPC-46B": "general diary",
    "CrPC-46C": "designate a police-officer",
    "CrPC-46E": "medical officer",
    "CrPC-50": "more restraint than is necessary",
    "CrPC-51": "search such person",
    "CrPC-52": "another woman",
    "CrPC-54": "without warrant, arrest",
    "CrPC-54A": "communicate to him the reasons",
    "CrPC-56": "order in writing",
    "CrPC-60": "without unnecessary delay",
    "CrPC-61": "twenty-four hours",
    "CrPC-87": "absconded",
    "CrPC-88": "attachment",
    "CrPC-107": "keeping the peace",
    "CrPC-144": "abstain from a certain act",
    "CrPC-145": "breach of the peace",
    "CrPC-154": "reduced to writing",
    "CrPC-155": "non-cognizable",
    "CrPC-156": "without the order of a magistrate",
    "CrPC-160": "require the attendance",
    "CrPC-161": "bound to answer",
    "CrPC-162": "be signed by the person making it",
    "CrPC-163": "inducement",
    "CrPC-164": "confession",
    "CrPC-167": "twenty-four hours",
    "CrPC-167A": "shown arrested",
    "CrPC-190": "take cognizance",
    "CrPC-200": "upon oath the complainant",
    "CrPC-202": "postpone the issue of process",
    "CrPC-203": "dismiss the complaint",
    "CrPC-241A": "groundless",
    "CrPC-247": "does not appear",
    "CrPC-248": "withdraw his complaint",
    "CrPC-250": "frivolous or vexatious",
    "CrPC-337": "pardon",
    "CrPC-339B": "absconded",
    "CrPC-342": "refusing to answer",
    "CrPC-352": "open court",
    "CrPC-403": "tried again for the same offence",
    "CrPC-417": "acquittal",
    "CrPC-417A": "inadequacy",
    "CrPC-491": "illegally or improperly detained",
    "CrPC-494": "withdraw from the prosecution",
    "CrPC-496": "released on bail",
    "CrPC-497": "non-bailable",
    "CrPC-498": "not be excessive",
    "CrPC-517": "disposal",
    "CrPC-561A": "inherent power",
}


class Slice(StrEnum):
    DIRECT_LOOKUP = "direct_lookup"
    MULTI_SECTION = "multi_section"
    AMENDED = "amended"
    UNANSWERABLE = "unanswerable"
    AMBIGUOUS = "ambiguous"
    BANGLA = "bangla"


class GoldQuestion(BaseModel):
    id: str
    question: str
    language: str = "en"
    slice: Slice
    gold_sections: list[str] = Field(default_factory=list)
    answerable: bool
    requires_acts: list[str] = Field(default_factory=list)
    notes: str = ""
    verified_against: str

    @field_validator("gold_sections")
    @classmethod
    def _well_formed(cls, value: list[str]) -> list[str]:
        for item in value:
            if "-" not in item:
                raise ValueError(f"gold section {item!r} must look like 'CrPC-54'")
        return value

    @property
    def targets(self) -> list[tuple[str, str]]:
        """(act_code, section_number) pairs, splitting on the first hyphen only so
        that hyphenated section numbers such as CrPC-265-I survive."""
        return [tuple(item.split("-", 1)) for item in self.gold_sections]  # type: ignore[misc]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    question_id: str
    problem: str


def load_gold(path: pathlib.Path | None = None) -> list[GoldQuestion]:
    source = path or GOLD_PATH
    questions = [
        GoldQuestion.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seen: set[str] = set()
    for question in questions:
        if question.id in seen:
            raise ValueError(f"duplicate question id {question.id}")
        seen.add(question.id)
    return questions


def validate_against_corpus(
    questions: list[GoldQuestion], corpora: dict[str, object]
) -> list[ValidationIssue]:
    """Check every gold label resolves to a real, live section of a parsed act.

    `corpora` maps an act code to a parsed Act. Codes absent from it are treated as
    not-yet-ingested, which is an error only when the question claims to be
    answerable from them.
    """
    issues: list[ValidationIssue] = []

    for question in questions:
        if question.answerable and not question.gold_sections:
            issues.append(
                ValidationIssue(question.id, "answerable but has no gold sections")
            )
        if not question.answerable and question.gold_sections:
            issues.append(
                ValidationIssue(
                    question.id, "marked unanswerable but carries gold sections"
                )
            )

        for code, number in question.targets:
            if code not in ACT_CODES:
                issues.append(
                    ValidationIssue(question.id, f"unknown act code {code!r}")
                )
                continue
            act = corpora.get(code)
            if act is None:
                issues.append(
                    ValidationIssue(
                        question.id, f"act {code} not ingested; cannot verify {number}"
                    )
                )
                continue
            section = act.section(number)  # type: ignore[attr-defined]
            if section is None:
                issues.append(
                    ValidationIssue(
                        question.id, f"{code}-{number} does not exist in the corpus"
                    )
                )
            elif section.is_repealed:
                issues.append(
                    ValidationIssue(
                        question.id, f"{code}-{number} is a repealed section"
                    )
                )
            elif not section.text.strip():
                issues.append(
                    ValidationIssue(question.id, f"{code}-{number} has no text")
                )
            else:
                expected = SECTION_EXPECTATIONS.get(f"{code}-{number}")
                if expected and expected not in section.text.lower():
                    issues.append(
                        ValidationIssue(
                            question.id,
                            f"{code}-{number} no longer contains {expected!r}; "
                            "the label may point at the wrong provision, or the "
                            "source text has changed",
                        )
                    )

    return issues
