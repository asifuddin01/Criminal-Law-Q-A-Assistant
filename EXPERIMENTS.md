# Experiment Log

Each entry records the objective and hypothesis, the configuration, the result, the failure
cases examined, and the decision taken with its next step. Entries are appended, never
rewritten — an experiment whose hypothesis was wrong is more useful in the record than out
of it.

Evaluation methodology and metric definitions live in [eval/README.md](eval/README.md).

## Planned progression

The build advances through stages, each ending in a full evaluation run against the same
dataset so that every change is attributable to a number. The stages are listed here in
advance so that a stage producing no improvement is visibly a result rather than a gap.

| Stage | Change | Status |
|---|---|---|
| 0 | Harness, gold dataset, no retrieval | In progress |
| 1 | LLM-only baseline | Not started |
| 2 | Naive fixed-size chunking, dense retrieval | Not started |
| 3 | Legal-aware chunking on section boundaries | Not started |
| 4 | Hybrid retrieval (BM25 + dense, RRF) | Not started |
| 5 | Reranking | Not started |
| 6 | Prompt and refusal behaviour | Not started |
| 7 | Citation validation gate | Not started |
| 8 | Amendment-aware retrieval | Not started |

Stage 1 exists to establish the hallucination floor. A retrieval system that cannot beat a
bare model on citation accuracy is not earning its complexity, and without the baseline that
claim cannot be made either way.

## Results summary

Populated as stages complete. Retrieval recall, citation precision, answer faithfulness and
refusal accuracy are reported per stage against the frozen gold set.

| Stage | Recall@10 | Citation precision | Faithfulness | Refusal accuracy |
|---|---|---|---|---|
| — | — | — | — | — |

## Entries

### 2026-09-10 — Source survey before ingestion design

**Objective.** Establish the structure of the source corpus before designing ingestion.

**Hypothesis.** Bangladesh legislation on `bdlaws.minlaw.gov.bd` is published per section,
so a per-section crawl maps cleanly onto the citation unit.

**Method.** Direct inspection of the live site: the table of contents, a representative
section page (`section-26048`, s.4 Definitions), and the act-level endpoints.

**Result.** The hypothesis was half right and consequentially wrong. Per-section endpoints
exist but their unit is the *marginal note*, not the section: 594 links for 565 sections,
with s.1 spanning two pages and s.3 spanning four, and continuation pages carrying no
section number. A crawl over these would fragment sections and emit citations with no
section attached.

A single-document endpoint, `/act-print-75.html`, serves the whole act — 554,400 characters,
sections 1 to 565, 599 amendment footnotes — with section grouping preserved.

**Failure case examined.** The page for `section-14269` renders as the marginal note
"Extent" followed by provision text. Nothing in the body identifies it as s.1(2). Any
retrieval system built on these pages would answer questions about the territorial extent of
the Code while citing a source called "Extent".

**Decision.** Ingest from the single-document print view. ADR 0002 superseded by ADR 0005
before either was implemented.

**Next step.** Build the parser against the print view, with tests asserting the recovered
section count and spot-checking irregular boundaries — lettered sections (4A, 46B) and
repealed sections carrying no body text.
