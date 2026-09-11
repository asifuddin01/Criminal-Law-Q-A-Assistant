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
| 1 | LLM-only baseline | Done |
| 2 | Naive fixed-size chunking, dense retrieval | Complete on both models |
| 3 | Legal-aware chunking on section boundaries | Complete on local model; hosted run pending quota |
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

| Stage | Recall@10 | Citation precision | Excerpt validity | Refusal accuracy |
|---|---|---|---|---|
| 1 — LLM only | n/a (no retrieval) | 18.4% | **0.0%** | 85.0% |
| 2 — naive chunks | 48.6% | 54.9% | 74.6% | 71.6% |
| 3 — legal-aware chunks | **90.3%** (retrieval-only) | pending | pending | pending |

Hosted stage 2 is now complete at 95 of 95 measured, zero errors, after the harness
learned to sleep through the daily budget and resume from cache.

**Complete progression on the local model** (`qwen2.5:3b-instruct`, all three stages,
93-94 of 95 measured each). Absolute quality is lower than the hosted model, but the
model is constant across stages, so the movement is attributable to the pipeline:

| Stage | Retrieval recall | Citation precision | Answer hit rate | Excerpt validity | Refusal accuracy |
|---|---|---|---|---|---|
| 1 — LLM only | n/a | 7.4% | 1.4% | 0.0% | 71.0% |
| 2 — naive chunks | 48.6% | 36.8% | 36.1% | 49.4% | 83.0% |
| 3 — legal-aware chunks | **88.6%** | **80.8%** | **80.0%** | 53.2% | 86.0% |

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

### 2026-09-10 — Stage 1: LLM-only baseline

**Objective.** Establish the floor. A retrieval system that cannot beat an unassisted
model on citation accuracy is not earning its complexity, and without this measurement
that claim cannot be made in either direction.

**Hypothesis.** A large instruction model will produce fluent, roughly correct answers
about criminal procedure but cite unreliably, because it has no access to the text.

**Configuration.** `openai/gpt-oss-120b` on Groq, temperature 0, 2500 max tokens,
concurrency 2. All 95 gold questions, prompted to answer and cite exactly as the
finished system will, so later stages compare like for like. No corpus, no retrieval.

**Result.** 93 of 95 measured; 2 lost to rate limits and excluded from every rate.

| Metric | Value |
|---|---|
| Citations made | 171 |
| Citation existence | 86.6% |
| Hallucinated citation rate | 13.5% |
| Citation precision | 18.4% |
| Answer hit rate | 25.7% |
| **Excerpt validity** | **0.0%** (0 valid of 143 checked) |
| Refusal accuracy | 85.0% |
| Refused when unanswerable | 43.5% |
| Refused when answerable | 1.4% |

| Slice | n | Errors | Refusal accuracy | Has a correct citation |
|---|---|---|---|---|
| direct_lookup | 40 | 1 | 97.4% | 20.5% |
| multi_section | 12 | 1 | 100% | 45.5% |
| amended | 10 | 0 | 100% | 20.0% |
| bangla | 10 | 0 | 100% | 30.0% |
| unanswerable | 14 | 0 | 71.4% | — |
| ambiguous | 9 | 0 | **0.0%** | — |

**Failure cases examined.**

*It answers from the wrong country's statute.* This is the dominant failure and it was
not the one anticipated. The model consistently cites **Indian** Code of Criminal
Procedure, 1973 numbering: s.41 for arrest without warrant (Bangladesh: s.54), s.57 for
the twenty-four hour limit (s.61), s.437-439 for bail (s.496-498), s.321 for withdrawal
from prosecution (s.494), s.374-386 for appeals. The substance is frequently right — it
correctly states the twenty-four hour rule — while the citation points into a different
statute. The two codes share ancestry, so a minority of numbers coincide (s.156 for
investigation into cognizable cases is the same in both), which is why precision is 18%
rather than near zero.

*Every quoted excerpt is fabricated.* 143 quotes were checked against the text of the
section they were attributed to. **None matched.** Not one. The quotations are fluent,
plausible, correctly styled as statutory prose, and invented — for example
`"Every person who is arrested without warrant shall be produced before a magistrate
within twenty-four hours"` attributed to s.57, which is neither the wording nor the
section. This is the single clearest argument for the citation validation gate, and it
is a deterministic check requiring no judge.

*It never asks for clarification.* On all nine ambiguous questions the model answered
rather than asking what was meant: 0% refusal accuracy on that slice. "Can I get bail?"
produced citations to three bail provisions with no idea what offence was involved.
"What are my rights?" was answered outright. A system that never asks is a system that
guesses.

*It answers most questions it cannot answer.* Only 43.5% of unanswerable questions were
declined, so the majority received a confident answer drawn from nothing. Conversely it
almost never refuses wrongly (1.4%), so the bias is entirely toward answering.

**The metric pair that matters.** Citation existence is 86.6% while precision is 18.4%.
A naive hallucination check — does the cited section exist? — reports the system as
mostly fine, on answers that are largely miscited. Existence and precision measure
different things and both are needed. Excerpt validity, meanwhile, collapses to zero and
is the most damning number in the table.

**Two measurement bugs found by running this, not by reading it.**

Errored questions were scored as correct decisions. An errored answer carries
`refused=False`, so on an answerable question `refused != answerable` is true, and 40
rate-limit failures counted as sound refusal judgment. Refusal accuracy read 83.2% over
a run in which only 55 questions were actually measured. Rates now cover measured
questions only and six tests pin the behaviour.

Empty completions were scored as answers with no citations. `gpt-oss` spends completion
tokens on reasoning before emitting content, so a budget sized for the answer alone
returned an empty string with `finish_reason: stop`. At 900 tokens it produced 169
characters of content; at 2500, a full answer. A truncation bug was presenting as a
model result.

**Decision.** Baseline recorded. These are the numbers every later stage is measured
against, and three of them — 18.4% precision, 0.0% excerpt validity, 0% clarification
on ambiguous questions — define what retrieval and the citation gate have to fix.

**Next step.** Stage 2: naive fixed-size chunking with dense retrieval. Deliberately the
crude version, so that stage 3's legal-aware chunking is measured against it rather than
asserted to be better.

### 2026-09-11 — Retrieval-only comparison of chunking strategies

**Objective.** Measure the effect of chunking on retrieval, isolated from generation.

**Hypothesis.** Chunking on section boundaries improves retrieval, because the section
is the unit a question is asked about and the unit a citation names.

**Method.** Both indexes built over the same act with the same embedding model, and the
72 answerable gold questions run through each. **No model in the loop**, so any
difference is attributable to chunking and nothing else — and it costs no provider
quota, which turned out to matter (see the rate-limit entry below).

**Result.** The largest single improvement measured so far.

| Strategy | Chunks | R@1 | R@3 | R@5 | R@8 | R@10 | R@20 |
|---|---|---|---|---|---|---|---|
| naive_fixed_size | 465 | 20.8% | 40.3% | 41.7% | 51.4% | 52.8% | 58.3% |
| legal_aware | 621 | **61.1%** | **76.4%** | **84.7%** | **88.9%** | **90.3%** | **95.8%** |

Recall@1 nearly triples. Recall@10 rises from roughly half the questions to nine in ten.
Since recall is the ceiling on the whole system — generation cannot cite a section
retrieval never returned — the naive pipeline was capped at 52.8% no matter how good the
prompt or the model.

| Slice | naive R@10 | legal-aware R@10 |
|---|---|---|
| direct_lookup | 52.5% | **100%** |
| multi_section | 83.3% | **100%** |
| amended | 30.0% | **90.0%** |
| bangla | 40.0% | **40.0%** |

**Failure cases examined.**

*Half the naive strategy's successes were fragile.* Of the questions it did answer, 26
had their gold section delivered by a chunk that crosses a section boundary — the right
words arriving under a label that may belong to a neighbouring provision. The
legal-aware strategy: zero. So the gap is wider than recall alone shows, because a
boundary-crossing hit is a hit whose citation cannot be trusted.

*The Bangla slice did not move at all.* 40.0% under both strategies — the only slice
where legal-aware chunking changed nothing. This is informative rather than
disappointing: cross-lingual retrieval is not limited by how the text is divided but by
whether the embedding model places a Bangla question near English statutory text. It is
a different bottleneck needing a different fix, and no amount of chunking work will
touch it. Candidate responses: a stronger multilingual embedding model, query
translation before retrieval, or ingesting the Bangla texts of the acts. To be settled
by measurement, not chosen now.

*Amended provisions were the naive strategy's worst non-Bangla slice* at 30%. Amended
sections carry dense footnote markers and bracketed insertions, so their text is
irregular; fixed windows cut through those structures where section-bounded chunks do
not.

**Decision.** Legal-aware chunking adopted. ADR 0002's reasoning is now supported by a
measurement rather than an argument.

**Next step.** Stage 3 generation, once provider quota resets.

### 2026-09-11 — Provider rate limits, and a run that looked like a result

**What happened.** The stage 2 generation sweep failed 34 of 95 questions. The failures
were not distributed randomly: because the harness runs the dataset in order and the
budget depletes as it goes, they landed on whichever slices come last. The ambiguous
slice lost 9 of 9 and the Bangla slice 10 of 10, while direct_lookup lost 2 of 40.

The error accounting added in stage 1 correctly excluded those questions from the rates.
That was not enough. Excluding a *biased* sample still leaves a biased measurement:
"refused when unanswerable: 100%" was computed over three questions, and two slices had
no data at all. The run printed a clean-looking table.

**Diagnosis.** Two separate limits, discovered in that order:

- **8,000 tokens per minute**, identical across every model on the catalogue, so there
  is no model to switch to for headroom. Retrieval context of roughly 2,900 tokens per
  question exhausts it within a minute.
- **200,000 tokens per day**, and this one is **per model**. `gpt-oss-120b` was spent
  (199,180 used) while `gpt-oss-20b` and `qwen3.8-27b` remained fresh.

**Correction.** A continuously refilling token bucket paces requests against the
per-minute budget, reserving on the prompt plus a realistic completion rather than the
max_tokens ceiling, and reconciling against reported usage afterwards. The per-day limit
cannot be paced around, so the harness now detects it, stops immediately, and **writes no
results** — a partial sweep is worse than no sweep, because it looks like a measurement.

**What this changed about method.** The retrieval-only evaluation above was built in
response: it answers the question that actually mattered — does legal-aware chunking
help? — with no model in the loop, no quota consumed, and no confound from generation.
The constraint produced a better experiment than the one originally planned, because it
forced the variable to be isolated.

### 2026-09-11 — Complete three-stage progression on the local model

**Objective.** Obtain a complete, internally consistent progression across all three
stages while the hosted model's daily budget was spent.

**Configuration.** `qwen2.5:3b-instruct` via Ollama, same 95 questions, same indexes,
same prompts, same `k=8`. Roughly 10 seconds per question, so about 16 minutes per
stage. The model is held constant across all three stages, which is what makes the
movement attributable to the pipeline rather than to the model.

**Result.** 93 to 94 of 95 measured at each stage.

| Metric | Stage 1 | Stage 2 | Stage 3 | Change |
|---|---|---|---|---|
| Retrieval recall | n/a | 48.6% | **88.6%** | +40.0 pts |
| Citation precision | 7.4% | 36.8% | **80.8%** | ×10.9 |
| Answer hit rate | 1.4% | 36.1% | **80.0%** | ×57 |
| Hallucinated citation rate | 8.6% | 0.0% | **0.0%** | eliminated |
| Excerpt validity | 0.0% | 49.4% | 53.2% | +53.2 pts |
| Refusal accuracy | 71.0% | 83.0% | **86.0%** | +15.0 pts |

Citation precision rises elevenfold and answer hit rate fifty-sevenfold. Fabricated
section numbers are eliminated entirely the moment retrieval is introduced, because a
model given real sections stops inventing them.

**Failure cases examined.**

*Excerpt validity stalls near half.* It moves from 0% to 49.4% with retrieval and then
barely at all — 53.2% — with better chunking. Roughly half of all quotations remain
paraphrases of text the model was actually shown. Better retrieval cannot fix this:
the model has the correct text in front of it and reflows it anyway. This is precisely
the gap the citation validation gate exists to close, and it closes it deterministically
rather than by asking the model to try harder. It also means the gate is not
belt-and-braces on a solved problem — at stage 3 it is still stripping about half the
quotations offered.

*Retrieval makes the system more willing to answer what it cannot.* Refusals on
genuinely unanswerable questions fall as the pipeline improves: 69.6% at stage 1, 63.6%
at stage 2, 56.5% at stage 3. Retrieval always returns something, and something is
enough for the model to construct an answer around. Overall refusal accuracy still rises
because false refusals on answerable questions collapse from 28.6% to 4.3%, but the
out-of-scope slice moves the wrong way. Better retrieval buys confidence, and confidence
is not free — a system that always has context will always find a reason to answer. The
fix is not more retrieval but a relevance floor: retrieved text that is merely the
nearest available is not the same as text that answers the question.

**Decision.** This is the reportable end-to-end progression. The hosted model's stages 1
and 2 remain the higher-quality track and will be completed when budget allows; the two
tracks are kept in separate result directories and are never plotted on one line, since
a stage-to-stage line spanning two models cannot distinguish pipeline improvement from
model quality.

**Next step.** Finish stage 2 and run stage 3 on the hosted model. Then a relevance
floor for the out-of-scope regression above.

### 2026-09-11 — Hosted stage 2 completed by waiting out the budget

**Result.** 95 of 95 measured, no errors, against the 62 of 95 that the earlier
partial sweep managed. The run slept through the per-day limit and resumed from
cache rather than stopping.

| Metric | Partial sweep (62/95) | Complete sweep (95/95) |
|---|---|---|
| Retrieval recall | 50.0% | 48.6% |
| Citation precision | 52.1% | 54.9% |
| Answer hit rate | 58.6% | 55.6% |
| Excerpt validity | 75.0% | 74.6% |
| Refusal accuracy | 77.4% | **71.6%** |

Most figures barely moved, which is reassuring about the ones that did. Refusal
accuracy fell by nearly six points once the missing questions were measured, because
the slices the partial sweep lost were exactly the ones that test refusal: ambiguous
(9 of 9 lost) and unanswerable (11 of 14 lost). The partial number was not noisy, it
was biased — and biased in the flattering direction, which is the direction that does
not prompt investigation.

That is the concrete case for refusing to write results from an incomplete sweep. Had
the partial numbers been reported, the system would have looked six points better at
the one behaviour it is least good at.

