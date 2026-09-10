"""Validate the gold dataset against the parsed corpus.

    python -m app.evaluation
"""

from __future__ import annotations

import sys
from collections import Counter

from app.evaluation.dataset import load_gold, validate_against_corpus
from app.ingest import cache_path, parse_act


def main() -> int:
    questions = load_gold()

    corpora = {}
    crpc_cache = cache_path(75)
    if crpc_cache.exists():
        corpora["CrPC"] = parse_act(
            crpc_cache.read_text(encoding="utf-8", errors="replace"),
            act_id=75,
            source_url="https://bdlaws.minlaw.gov.bd/act-print-75.html",
        )

    print(f"loaded {len(questions)} questions")
    for name, count in sorted(Counter(q.slice.value for q in questions).items()):
        print(f"  {name:<16} {count:>3}")

    issues = validate_against_corpus(questions, corpora)
    if not issues:
        labels = sum(len(q.gold_sections) for q in questions)
        print(f"\nOK: {labels} gold labels resolve against the parsed corpus")
        return 0

    print(f"\n{len(issues)} problem(s):")
    for issue in issues:
        print(f"  {issue.question_id}: {issue.problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
