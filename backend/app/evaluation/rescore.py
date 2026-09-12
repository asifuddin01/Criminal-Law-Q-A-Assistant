"""Re-score a recorded run without asking the model again.

    python -m app.evaluation.rescore --run stage-2
    python -m app.evaluation.rescore --all --dry-run

A score is derived from an answer. When the scorer is corrected — and it has been
— every run recorded under the old one is reporting a number nobody would stand
behind, and the obvious remedy, re-running, is the wrong one: it spends a hosted
budget to re-measure text that has not changed, and it conflates two variables,
because the new run also has a new prompt and a new corpus.

Answers are therefore stored beside the scores, and this re-derives the scores from
them. What changes is the measurement and only the measurement.

A run re-scored here records `rescored_with` in its summary, so a number produced by
a later scorer than the run it belongs to is never silently mistaken for the
original.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import asdict

from app.evaluation.dataset import load_gold
from app.evaluation.harness import RUNS_DIR
from app.evaluation.metrics import aggregate, score_question
from app.ingest import cache_path, parse_act, parse_schedule, schedule_path
from app.qa.schema import Answer, Citation
from app.retrieval.chunking import ACT_DOCUMENTS, document_for

# Bumped when the scorer changes in a way that moves numbers. Recorded in every
# summary this writes, so two rows in one table can be told apart.
SCORER_VERSION = "2026-09-12-trimmed-prefix"


def _load_answers(run: pathlib.Path) -> dict[str, Answer]:
    path = run / "answers.jsonl"
    if not path.exists():
        return {}
    answers: dict[str, Answer] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        question_id = record.pop("question_id")
        record["citations"] = [Citation(**c) for c in record.get("citations", [])]
        answers[question_id] = Answer(**record)
    return answers


def _corpora() -> tuple[dict, list]:
    corpora = {}
    for act_id in sorted(ACT_DOCUMENTS):
        path = cache_path(act_id)
        if path.exists():
            corpora[document_for(act_id)] = parse_act(
                path.read_text(encoding="utf-8", errors="replace"),
                act_id=act_id,
                source_url=f"https://bdlaws.minlaw.gov.bd/act-print-{act_id}.html",
            )
    entries = parse_schedule(schedule_path()) if schedule_path().exists() else []
    return corpora, entries


def rescore(run: pathlib.Path, *, dry_run: bool = False) -> int:
    summary_path = run / "summary.json"
    if not summary_path.exists():
        print(f"{run.name}: no summary.json")
        return 2

    answers = _load_answers(run)
    if not answers:
        print(
            f"{run.name}: no answers.jsonl — this run predates answer recording and "
            f"cannot be re-scored without re-running it"
        )
        return 2

    previous = json.loads(summary_path.read_text(encoding="utf-8"))
    corpora, entries = _corpora()

    scores = []
    for question in load_gold():
        answer = answers.get(question.id)
        if answer is None:
            continue
        scores.append(score_question(question, answer, corpora, schedule=entries))

    summary = aggregate(scores)
    for key in (
        "stage", "system", "provider", "model", "elapsed_seconds",
        "cache_hits", "partial",
    ):
        if key in previous:
            summary[key] = previous[key]
    summary["rescored_with"] = SCORER_VERSION

    # Coverage, stated rather than implied. The gold set has grown since the hosted
    # runs were recorded, so a re-scored run can cover fewer questions than the
    # dataset now holds. Reporting its rates against the current dataset size would
    # claim a completeness it does not have, and reporting only its own count would
    # hide that the comparison is against a smaller set.
    summary["dataset_questions"] = len(load_gold())
    summary["missing_answers"] = summary["dataset_questions"] - len(scores)
    if summary["missing_answers"]:
        print(
            f"    note: {summary['missing_answers']} of "
            f"{summary['dataset_questions']} questions have no answer in this run "
            f"(added to the dataset after it was recorded); every rate below covers "
            f"the {len(scores)} it does have"
        )

    def pct(value):
        return "n/a" if value is None else f"{value * 100:.1f}%"

    print(f"{run.name}: {len(scores)} answers re-scored")
    for label, key in (
        ("excerpt validity", "excerpt_validity"),
        ("  matched as written", "excerpt_validity_unrepaired"),
        ("misattribution rate", "misattribution_rate"),
        ("fabrication rate", "fabrication_rate"),
        ("citation existence", "citation_existence"),
        ("citation precision", "citation_precision"),
        ("answer hit rate", "answer_hit_rate"),
    ):
        before = previous.get(key)
        after = summary.get(key)
        arrow = "" if before == after else f"   ({pct(before)} -> {pct(after)})"
        print(f"    {label:<22}{pct(after)}{arrow}")

    if dry_run:
        return 0

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (run / "per_question.jsonl").open("w", encoding="utf-8") as handle:
        for question in load_gold():
            answer = answers.get(question.id)
            if answer is None:
                continue
            score = next(s for s in scores if s.question_id == question.id)
            handle.write(
                json.dumps(
                    {
                        **asdict(score),
                        "question": question.question,
                        "gold_sections": question.gold_sections,
                        "answer_text": answer.text[:600],
                        "cited": [c.section for c in answer.citations],
                        "retrieved_sections": answer.retrieved_sections,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-score a recorded run.")
    parser.add_argument("--run", help="run directory name, e.g. stage-2-ollama")
    parser.add_argument("--all", action="store_true", help="every complete run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.all:
        runs = sorted(p for p in RUNS_DIR.glob("stage-*") if p.is_dir())
    elif args.run:
        runs = [RUNS_DIR / args.run]
    else:
        parser.error("pass --run <name> or --all")

    worst = 0
    for run in runs:
        worst = max(worst, rescore(run, dry_run=args.dry_run))
    return 0 if args.all else worst


if __name__ == "__main__":
    sys.exit(main())
