# Evaluation

## Principle

A single score at the end of the project says almost nothing. The same dataset is run after
every stage, so each change is attributable to a movement in a number, and a change that
moves nothing is recorded as such.

Alongside the aggregates, a small number of failures are examined in full at each stage.
Aggregate metrics say whether a system got better; failure cases say why, and they are what
determine the next change.

## Metrics

| Metric | Definition | Why it is measured |
|---|---|---|
| **Recall@k** | Fraction of questions where at least one gold section appears in the top *k* retrieved chunks | Upper bound on answerable questions. Generation cannot recover what retrieval missed. |
| **Citation precision** | Of sections cited in the answer, the fraction that are both correct and actually present in the retrieved context | Directly measures the failure this system exists to avoid: confident citation of the wrong provision. |
| **Faithfulness** | Fraction of answer claims supported by the cited text | Catches answers that cite a real section but assert something it does not say. |
| **Refusal accuracy** | Correct refusals plus correct answers, over all questions, on the unanswerable slice | The brief requires handling of ambiguous and unsupported questions. Unmeasured refusal behaviour tends to collapse into either never refusing or refusing everything. |
| **Excerpt validity** | Fraction of quoted excerpts that are exact substrings of stored source text | A cheap, deterministic check that catches fabricated quotations without a model in the loop. |

Recall@k and excerpt validity are deterministic. Citation precision is deterministic given
gold section labels. Faithfulness requires judgement and is scored by an LLM judge against a
rubric, with a manually scored subset each stage to check the judge has not drifted.

## Dataset

`dataset/gold.jsonl` — one JSON object per line:

```json
{
  "id": "q-0001",
  "question": "Who may arrest without a warrant?",
  "language": "en",
  "gold_sections": ["CrPC-54"],
  "answerable": true,
  "category": "arrest",
  "notes": "s.54 enumerates the cases; see also s.55",
  "verified_against": "https://bdlaws.minlaw.gov.bd/act-print-75.html"
}
```

### Construction protocol

Gold section labels are **verified against the fetched act text**, never recalled from
memory. A wrong gold label is worse than a missing question: it silently penalises correct
retrieval and rewards incorrect retrieval, and it does so invisibly, because nothing in the
pipeline can detect it.

Every entry therefore records `verified_against`, and the harness fails loudly on any entry
whose `gold_sections` do not resolve to sections present in the ingested corpus.

### Slices

The dataset is stratified so that per-slice results are meaningful, not just the aggregate:

- **Direct lookup** — the answer sits in one section.
- **Multi-section** — the answer requires combining provisions.
- **Amended provisions** — the current text differs from the 1898 original, testing whether
  the system cites current law.
- **Unanswerable** — plausible criminal-law questions the corpus genuinely does not answer.
  The correct behaviour is refusal.
- **Ambiguous** — questions admitting several readings, where the correct behaviour is to
  ask for clarification or answer under a stated interpretation.
- **Bangla** — questions posed in Bangla against the English corpus, per the cross-lingual
  requirement.

The unanswerable and ambiguous slices are not padding. A system tuned only on answerable
questions reliably learns to always answer.

## Running

```bash
cd backend && uv run python -m eval.harness --stage <n>
```

Results are written to `runs/stage-<n>/` as both a machine-readable summary and a
per-question breakdown, and the summary table in
[EXPERIMENTS.md](../EXPERIMENTS.md) is updated from them.

Model responses are cached by prompt hash so that re-running after an unrelated change does
not re-spend free-tier quota.

## Status

Metric definitions and dataset schema are fixed. Dataset construction begins once the
ingestion pipeline can resolve section identifiers, so that every gold label can be
validated against real ingested text at the moment it is written.
