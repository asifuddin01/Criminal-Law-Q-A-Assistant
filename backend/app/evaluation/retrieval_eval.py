"""Retrieval-only evaluation.

    python -m app.evaluation.retrieval_eval

Measures what retrieval puts in front of the model, with no model in the loop. This
isolates the chunking strategy from generation entirely — a change in recall here is
attributable to chunking and nothing else — and it costs no provider quota, so it can
be run as often as the strategy changes.

Recall is an upper bound on the whole system: generation cannot cite a section that
retrieval never returned.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

from app.evaluation.dataset import load_gold
from app.retrieval import VectorIndex

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "eval" / "runs" / "retrieval"
CUTOFFS = (1, 3, 5, 8, 10, 20)


def evaluate(strategy: str) -> dict:
    index = VectorIndex.load(strategy)
    questions = [q for q in load_gold() if q.answerable and q.gold_sections]
    largest = max(CUTOFFS)

    hits = {k: 0 for k in CUTOFFS}
    by_slice: dict[str, dict] = collections.defaultdict(
        lambda: {"n": 0, **{f"hit@{k}": 0 for k in CUTOFFS}}
    )
    boundary_crossing_hits = 0
    misses: list[dict] = []

    for question in questions:
        gold = {number for _, number in question.targets}
        results = index.search(question.question, k=largest)

        ranked: list[str] = []
        for hit in results:
            if hit.chunk.section_number not in ranked:
                ranked.append(hit.chunk.section_number)

        bucket = by_slice[question.slice.value]
        bucket["n"] += 1
        for k in CUTOFFS:
            if gold & set(ranked[:k]):
                hits[k] += 1
                bucket[f"hit@{k}"] += 1

        # A hit delivered by a chunk that spans a section boundary is fragile: the
        # text supporting it may belong to a neighbouring section.
        for hit in results[:10]:
            if hit.chunk.section_number in gold and hit.chunk.crosses_section_boundary:
                boundary_crossing_hits += 1
                break

        if not (gold & set(ranked[:10])):
            misses.append(
                {
                    "id": question.id,
                    "question": question.question[:90],
                    "gold": sorted(gold),
                    "top5": ranked[:5],
                }
            )

    total = len(questions)
    return {
        "strategy": strategy,
        "chunks": len(index),
        "model": index.model_name,
        "questions": total,
        "recall": {f"@{k}": round(hits[k] / total, 4) for k in CUTOFFS},
        "hits_via_boundary_crossing_chunk": boundary_crossing_hits,
        "by_slice": {
            name: {
                "n": data["n"],
                **{
                    f"recall@{k}": round(data[f"hit@{k}"] / data["n"], 4)
                    for k in (1, 5, 10)
                },
            }
            for name, data in sorted(by_slice.items())
        },
        "misses_at_10": misses,
    }


def main() -> int:
    strategies = [s for s in ("naive_fixed_size", "legal_aware") if VectorIndex.exists(s)]
    if not strategies:
        print("no indexes built; run: python -m app.retrieval.build --strategy legal_aware")
        return 2

    results = [evaluate(s) for s in strategies]

    header = f"{'strategy':<20}{'chunks':>8}" + "".join(
        f"{'R@' + str(k):>8}" for k in CUTOFFS
    )
    print(header)
    print("-" * len(header))
    for result in results:
        row = f"{result['strategy']:<20}{result['chunks']:>8}"
        row += "".join(f"{result['recall']['@' + str(k)] * 100:>7.1f}%" for k in CUTOFFS)
        print(row)

    print(f"\n{'slice':<18}" + "".join(f"{s['strategy'][:14]:>18}" for s in results))
    slice_names = sorted({n for r in results for n in r["by_slice"]})
    for name in slice_names:
        row = f"{name:<18}"
        for result in results:
            data = result["by_slice"].get(name)
            row += f"{(data['recall@10'] * 100 if data else 0):>17.1f}%"
        print(row)

    for result in results:
        print(
            f"\n{result['strategy']}: {len(result['misses_at_10'])} questions with no "
            f"gold section in the top 10; "
            f"{result['hits_via_boundary_crossing_chunk']} hits came via a chunk that "
            f"crosses a section boundary"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nwritten to {(OUT_DIR / 'summary.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
