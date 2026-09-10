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
| 0 | Harness, gold dataset, no retrieval | Done |
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

### 2026-09-10 — Ingestion parser for the print view

**Objective.** Parse `act-print-75.html` into sections and amendment records, with
section identity correct enough to cite.

**Hypothesis.** The print view's two-column marginal-note layout is regular, so
segmentation is a matter of detecting a section number at the start of each unit.

**Method.** Write the detector, run it against the full document, and compare the
recovered section list against the source rather than inspecting a sample.

**Result.** The layout is regular. Section *identity* is not. Five conventions each
corrupt it silently, and the count converged only after all five were handled:

| Iteration | Sections | What was wrong |
|---|---|---|
| 1 | 472, out of order | Footnote markers read as section numbers |
| 2 | 449 | Ordering fixed; whole-section amendment brackets rejected |
| 3 | 509 | Brackets handled; hyphenated and paired sections still lost |
| 4 | **522** | All conventions handled |

Final: **522 sections, 599 amendment records**, parsed in 0.56 s. Of the amendments,
320 are substitutions, 127 omissions, 124 insertions; 223 carry an explicit effective
date and 232 resolve to the amending act's own bdlaws id.

**Failure cases examined.**

*Section 54 disappeared.* The most consequential provision in the Code for arrest
questions. Its text opens with an amendment marker, so text extraction placed the
footnote number "74" where the section number belongs, and the section was filed
under a number that does not exist. 133 sections were lost this way. Extracting text
before stripping marker elements is the entire cause.

*Section 4 was marked repealed.* The definitions section — which supplies the
meanings of "bailable offence" and "cognizable offence" that the whole system depends
on — contains `(d) [Repealed by ...]` about a thousand characters in. That is a
repealed *clause* inside a live section. An unanchored search for a repeal bracket
marked the entire section repealed, which would have removed the Code's definitions
from the corpus while every count still looked plausible.

*Section 265-I welded onto 265K.* It hyphenates its letter where 265A through 265L do
not. Read as a continuation, its text became part of section 265K and would have been
quoted under that number — a citation that resolves, to the wrong provision.

*Sections 266-336 appear missing but are not.* They were replaced wholesale by the
265A-265L regime and are genuinely absent from the consolidation. A test now asserts
their absence, so a real corpus fact is not later re-investigated as a parser bug.

**Decision.** All five conventions handled and covered by tests, in two layers: a
handcrafted fixture that runs anywhere, and corpus tests asserting real counts that
skip when the source has not been fetched.

**What this changes about the evaluation plan.** Every one of these bugs produced a
corpus that looked healthy — plausible section counts, fluent text, resolving
citations — while being wrong about which provision was which. None would have been
caught by retrieval metrics, because retrieval would have succeeded against
mislabelled text. This is direct evidence for the decision in eval/README.md to verify
gold section labels against parsed text rather than recall them.

**Next step.** Build the gold evaluation set against the parsed corpus, now that
section identifiers resolve.

### 2026-09-10 — Gold evaluation dataset

**Objective.** Build the dataset every later stage is measured against, with labels
correct enough to trust.

**Hypothesis.** The risk here is not dataset size but label correctness. A wrong gold
label penalises correct retrieval and rewards incorrect retrieval, invisibly.

**Method.** Questions were derived *from* the corpus rather than written from memory
and matched to sections afterwards. The full text of every cited section was read
before a question citing it was written. Labels are then validated mechanically.

**Result.** 95 questions, 94 labels, all resolving against the parsed corpus.

| Slice | Questions |
|---|---|
| ambiguous | 9 |
| amended | 10 |
| bangla | 10 |
| direct_lookup | 40 |
| multi_section | 12 |
| unanswerable | 14 |

**Design decisions worth recording.**

*Unanswerability is relative to the corpus, not absolute.* "Is theft bailable?" is
unanswerable today only because Schedule II is a separate PDF that is not yet
ingested. Each unanswerable question records `requires_acts`, so these labels flip
correctly as the corpus grows rather than rotting into wrong labels. Four questions
depend on Schedule II specifically, which makes the gap from DATA_SOURCE finding 7
measurable rather than merely noted.

*24% of the dataset is unanswerable or ambiguous.* A dataset weighted toward
answerable questions teaches a system to always answer, which is precisely the
behaviour the brief asks us to avoid.

*Labels carry a content expectation, not just an identifier.* Resolution is a weak
check: a label can point at a real section that is simply the wrong one. Each
frequently cited section carries a distinctive phrase from its text, so a label that
drifts off its provision — or a source republished in different words — fails loudly.

*The validator has negative tests.* Two tests confirm it rejects a non-existent label
and a label pointing at the wrong provision. A validator that passes because it checks
nothing is worse than no validator, because it is trusted.

**Decision.** Dataset frozen for stage 1. 42 tests passing.

**Next step.** LLM-only baseline: run all 95 questions with no retrieval, to establish
the hallucination floor and the refusal behaviour of a bare model.
