"""Evaluation harness.

    python -m app.evaluation.harness --stage 1

Runs the gold dataset against a system under evaluation, scores every answer against
the parsed corpus, and writes both a summary and a per-question breakdown.

Model responses are cached by content hash. Re-running after an unrelated change
therefore costs nothing, which is what makes "run the dataset after every stage"
practical rather than aspirational on a free tier.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import sys
import time
from dataclasses import asdict

from app.evaluation.dataset import GoldQuestion, load_gold
from app.evaluation.metrics import QuestionScore, aggregate, score_question
from app.ingest import cache_path, parse_act
from app.llm import get_provider
from app.qa import Answer, BaselineLLM, Citation, RetrievalQA
from app.retrieval import VectorIndex

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUNS_DIR = REPO_ROOT / "eval" / "runs"
CACHE_DIR = REPO_ROOT / "data" / "cache" / "llm"

STAGES = {
    1: ("baseline-llm-only", "LLM only, no retrieval", None),
    2: ("rag-naive-chunks", "Dense retrieval, naive fixed-size chunks", "naive_fixed_size"),
    3: ("rag-legal-chunks", "Dense retrieval, legal-aware chunks", "legal_aware"),
}


def _cache_key(system: str, model: str, question: str) -> str:
    payload = f"{system}\x00{model}\x00{question}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_cache(key: str) -> Answer | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Answer(
        text=data["text"],
        citations=[Citation(**c) for c in data["citations"]],
        refused=data["refused"],
        model=data["model"],
        raw=data["raw"],
        error=data.get("error"),
        retrieved_sections=data.get("retrieved_sections", []),
    )


def _write_cache(key: str, answer: Answer) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(answer)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


class DailyBudgetExhausted(RuntimeError):
    """The provider's per-day token allowance is spent.

    Distinguished from a per-minute limit because they call for opposite responses:
    a per-minute limit is waited out within a run, a per-day one cannot be, and
    continuing only converts the remainder of the dataset into failures that land on
    whichever slices happen to come last.
    """


def _is_daily_limit(message: str) -> bool:
    return "tokens per day" in message.lower() or "TPD" in message


async def _run_one(
    system, question: GoldQuestion, model: str, semaphore, use_cache: bool
) -> tuple[Answer, bool]:
    key = _cache_key(system.name, model, question.question)
    if use_cache:
        cached = _read_cache(key)
        if cached is not None:
            return cached, True

    async with semaphore:
        answer = await system.answer(question.question)

    if answer.error and _is_daily_limit(answer.error):
        raise DailyBudgetExhausted(answer.error)

    if use_cache and not answer.error:
        _write_cache(key, answer)
    return answer, False


async def run_stage(
    stage: int, *, limit: int | None, concurrency: int, use_cache: bool
) -> int:
    if stage not in STAGES:
        print(f"stage {stage} is not implemented; available: {sorted(STAGES)}")
        return 2

    corpus_file = cache_path(75)
    if not corpus_file.exists():
        print("corpus not fetched; run: python -m app.ingest")
        return 2
    corpus = parse_act(
        corpus_file.read_text(encoding="utf-8", errors="replace"),
        act_id=75,
        source_url="https://bdlaws.minlaw.gov.bd/act-print-75.html",
    )

    questions = load_gold()
    if limit:
        questions = questions[:limit]

    provider = get_provider()
    name, description, strategy = STAGES[stage]

    if strategy is None:
        system = BaselineLLM(provider)
    else:
        if not VectorIndex.exists(strategy):
            print(
                f"index {strategy!r} not built; run: "
                f"python -m app.retrieval.build --strategy {strategy}"
            )
            return 2
        index = VectorIndex.load(strategy)
        print(f"index {strategy}: {len(index)} chunks, {index.model_name}")
        system = RetrievalQA(provider, index, name=name)

    model = getattr(provider, "_chat_model", "unknown")
    print(f"stage {stage}: {name} — {description}")
    print(f"provider {provider.name} / {model} · {len(questions)} questions\n")

    semaphore = asyncio.Semaphore(concurrency)
    started = time.perf_counter()
    try:
        results = await asyncio.gather(
            *(_run_one(system, q, model, semaphore, use_cache) for q in questions)
        )
    except DailyBudgetExhausted as exhausted:
        print(f"\nSTOPPED: {exhausted}")
        print(
            "The per-day token allowance is spent. Answers already obtained are "
            "cached, so re-running after the reset resumes rather than restarts.\n"
            "No results were written: a partial sweep biases whichever slices come "
            "last in the dataset."
        )
        return 3
    elapsed = time.perf_counter() - started

    scores: list[QuestionScore] = []
    cache_hits = 0
    for question, (answer, was_cached) in zip(questions, results, strict=True):
        cache_hits += int(was_cached)
        scores.append(score_question(question, answer, corpus))

    summary = aggregate(scores)
    summary["stage"] = stage
    summary["system"] = name
    summary["provider"] = provider.name
    summary["model"] = model
    summary["elapsed_seconds"] = round(elapsed, 1)
    summary["cache_hits"] = cache_hits

    destination = RUNS_DIR / f"stage-{stage}"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (destination / "per_question.jsonl").open("w", encoding="utf-8") as handle:
        for question, (answer, _), score in zip(questions, results, scores, strict=True):
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

    _report(summary)
    print(f"\nwritten to {destination.relative_to(REPO_ROOT)}/")
    return 0


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _report(summary: dict) -> None:
    print(f"{'questions':<32}{summary['questions']}")
    print(f"{'measured':<32}{summary['measured']}")
    print(f"{'errors':<32}{summary['errors']}")
    if summary["errors"]:
        print(
            f"{'':<32}rates below cover the "
            f"{summary['measured']} measured questions only"
        )
    print(f"{'citations made':<32}{summary['citations_made']}")
    print()
    for label, key in (
        ("retrieval recall", "retrieval_recall"),
        ("citation existence", "citation_existence"),
        ("hallucinated citation rate", "hallucinated_citation_rate"),
        ("citation precision", "citation_precision"),
        ("answer hit rate", "answer_hit_rate"),
        ("excerpt validity", "excerpt_validity"),
        ("refusal accuracy", "refusal_accuracy"),
        ("refused when unanswerable", "refused_when_unanswerable"),
        ("refused when answerable", "refused_when_answerable"),
    ):
        print(f"{label:<32}{_pct(summary[key])}")

    print(
        f"\n{'slice':<18}{'n':>4}{'err':>5}{'refusal acc':>14}{'has correct cite':>19}"
    )
    for name, bucket in sorted(summary["by_slice"].items()):
        hit = _pct(
            None
            if not bucket["measured"]
            else bucket["with_correct_citation"] / bucket["measured"]
        )
        print(
            f"{name:<18}{bucket['n']:>4}{bucket['errors']:>5}"
            f"{_pct(bucket['refusal_accuracy']):>14}{hit:>19}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the evaluation dataset.")
    parser.add_argument("--stage", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument(
        "--no-cache", action="store_true", help="ignore cached model responses"
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        run_stage(
            args.stage,
            limit=args.limit,
            concurrency=args.concurrency,
            use_cache=not args.no_cache,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
