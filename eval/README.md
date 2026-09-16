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
| **Answer hit rate** | Fraction of answerable questions where the answer cites at least one gold section | Whether the right provision reached the answer, not just the retrieved set. |
| **Refusal accuracy** | Correct refusals plus correct answers, over all questions, on the unanswerable slice | The brief requires handling of ambiguous and unsupported questions. Unmeasured refusal behaviour tends to collapse into either never refusing or refusing everything. |
| **Excerpt validity** | Fraction of quoted excerpts that are the cited section's own words | A cheap, deterministic check that catches fabricated quotations without a model in the loop. |
| **Excerpt validity (as written)** | The same, counting only excerpts that matched with no allowance made | Published beside the first so that the cost of each allowance is visible rather than absorbed. |
| **Citation existence** | Of sections cited, the fraction that exist in the document the citation names | Section numbers repeat across acts, so a citation resolved against the wrong document would be confirmed as readily as a right one. |

"Its own words" is not quite a raw substring test, and the difference is worth stating.
bdlaws' amendment brackets and its `[* * *]` marks are canonicalised away on both sides, and a
non-breaking hyphen (U+2011) is read as the hyphen it renders as; an ellipsis is read as an
elision and each segment checked in order, ignoring the punctuation at its edges; and a
citation label the model copied in front of the text is trimmed before the remainder is
required to match.
None of that admits a word the section does not contain — the stage 1 baseline, quoting from
memory, is rescued by none of it — and the reasoning is in
[ADR 0011](../docs/adr/0011-what-counts-as-a-verbatim-quotation.md).

A quotation that fails is reported as exactly one of four things, because they call for
different fixes: **misattributed** — real text from another section, a chunking failure;
**fabricated** — text found in no section, the model writing law; **over-elided** — the
cited section's own words in its order, cut to a piece too short to be evidence; and
**recomposed** — real pieces joined in an order the statute does not use, which states a
proposition the law does not. Excerpt validity and the four shares add up to 100%.

Every metric reported is deterministic. Recall@k, excerpt validity and citation existence
need no labels beyond the corpus itself; citation precision and answer hit rate are
deterministic given the gold section labels.

**On the faithfulness metric this file originally specified.** It was planned as an
LLM judge scoring "fraction of answer claims supported by the cited text" against a
rubric, with a manually scored subset each stage to check for drift. It was not built,
and the omission is deliberate rather than unfinished.

Two reasons. An LLM judge grading an LLM's answers shares the failure it is meant to
detect — both find the same fluent-but-unsupported prose plausible — and calibrating it
would take a manually scored subset large enough that scoring the whole set by hand
becomes the cheaper option. And the specific failure the judge was there to catch, an
answer asserting something its cited section does not say, is caught in its most
damaging form by the deterministic excerpt check: a claim attributed to statutory words
that do not exist in that section fails, with no model asked for an opinion.

What is not caught is an answer that quotes correctly and then characterises the quote
wrongly in its own prose. That gap is real, it is not measured, and it is listed in the
project's limitations rather than papered over with a number nobody has calibrated.

## Dataset

`dataset/gold.jsonl` — one JSON object per line:

```json
{
  "id": "q-0001",
  "question": "When may a police officer arrest a person without a warrant?",
  "language": "en",
  "slice": "direct_lookup",
  "gold_sections": ["CrPC-54"],
  "answerable": true,
  "requires_acts": ["CrPC"],
  "notes": "",
  "verified_against": "bdlaws act-print-75.html (2026-09-10 snapshot)"
}
```

`requires_acts` records which acts would answer a question. Unanswerability is
relative to the current corpus, not absolute: "is theft bailable?" was unanswerable while
Schedule II sat outside the corpus, and flipped to answerable when stage 4 brought it in.
The label moved because the dependency was recorded, not because somebody remembered to
revisit it — which is what keeps these labels correct as the corpus grows instead of
silently rotting into wrong ones.

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
# Validate every gold label against the parsed corpus
cd backend && uv run python -m app.evaluation

# Run the dataset against a stage (from stage 1 onward)
cd backend && uv run python -m app.evaluation.harness --stage <n>
```

Results are written to `runs/stage-<n>/` as both a machine-readable summary and a
per-question breakdown, and the summary table in
[EXPERIMENTS.md](../EXPERIMENTS.md) is updated from them.

Model responses are cached by prompt hash so that re-running after an unrelated change does
not re-spend free-tier quota.

## Validation

Labels are not trusted; they are checked, and the check is a hard failure.

`python -m app.evaluation` verifies that every gold label resolves to a section that
exists in the parsed corpus, is not repealed, and has text. Resolution alone is a weak
check — a label can point at a real section that is simply the wrong one — so each
frequently cited section also carries a distinctive phrase taken from its text at the
time the question was written. If a label stops pointing at the provision the question
was written against, or bdlaws republishes that section in different words, validation
fails loudly rather than quietly degrading every metric computed from it.

The validator is itself covered by negative tests, which confirm it rejects a
non-existent label and a label pointing at the wrong provision. A validator that
passes because it checks nothing is worse than none.

## Status

**101 questions**, every label validated against the parsed corpus:

| Slice | Questions |
|---|---|
| Direct lookup | 45 |
| Unanswerable | 15 |
| Multi-section | 12 |
| Amended provisions | 10 |
| Bangla | 10 |
| Ambiguous | 9 |

24 of the 101 are questions the corpus should not answer — the unanswerable slice plus the
ambiguous one, where the right behaviour is to ask what was meant rather than to pick a
reading.

The harness, the metrics and the re-scorer are built, and all four stages are measured on
both models. Results: [EXPERIMENTS.md](../EXPERIMENTS.md) and
[runs/charts/](runs/charts/).
