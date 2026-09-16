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
| 3 | Legal-aware chunking on section boundaries | Complete on both models |
| 4 | Full corpus: Schedule II and Penal Code, with structured offence lookup | Complete on both models |
| — | Hybrid retrieval (BM25 + dense, RRF) | **Planned, then dropped — see below** |
| — | Reranking | Not started |
| — | Prompt and refusal behaviour | Folded into stages 3 and 4 rather than run separately |
| — | Citation validation gate | Built from stage 2 onward, not staged separately |
| — | Amendment-aware retrieval | Not started |

Stage 1 exists to establish the hallucination floor. A retrieval system that cannot beat a
bare model on citation accuracy is not earning its complexity, and without the baseline that
claim cannot be made either way.

**Stage 4 was planned as hybrid retrieval and is not.** The reasoning for BM25 was that
statutory language is precise, and lexical matching on section numbers and defined terms
should matter as much as semantics. That reasoning was right about the problem and wrong
about the fix.

The failure it was aimed at is "is theft a bailable offence?", which embeds closest to the
sections *about* bail while the row that decides it ranks nowhere. BM25 would not have found
that row either: the question contains the word "theft" and the row's usefulness is that it
classifies an offence, not that it shares vocabulary with the question. What answers it is a
structured lookup of the offence by name in Schedule II — deterministic, and it either finds
the row or does not. That is what stage 4 became.

Hybrid retrieval remains untried rather than rejected, and is listed under future work. It is
recorded here because a plan that changes silently is indistinguishable from a plan that was
never followed.

## Results summary

Every run below was scored by one scorer (`rescore --all`), so rows are comparable with
each other rather than with whatever the scorer happened to be on the day each ran. Charts:
[eval/runs/charts/](eval/runs/charts/).

**Complete four-stage progression, local model** (`qwen2.5:3b-instruct`, 101 of 101
questions measured at every stage, no errors). The model is constant across stages, so the
movement is the pipeline:

| Stage | Retrieval recall | Citation precision | Answer hit rate | Excerpt validity | Refusal accuracy |
|---|---|---|---|---|---|
| 1 — LLM only | n/a | 6.9% | 1.3% | **0.0%** | 73.3% |
| 2 — naive chunks | 63.6% | 61.2% | 48.0% | 52.9% | 90.1% |
| 3 — legal-aware chunks | 80.5% | **66.3%** | **63.6%** | 83.9% | 88.1% |
| 4 — full corpus + offence lookup | **81.8%** | 59.1% | 61.0% | **87.5%** | **90.1%** |

**What a failed quotation actually was.** "Invalid excerpt" is two failures with opposite
fixes, and separating them is the clearest result in this table:

| Stage | Verified | Real text, wrong section | In no section at all |
|---|---|---|---|
| 1 — LLM only | 0.0% | 0.0% | **100.0%** |
| 2 — naive chunks | 52.9% | **18.6%** | 28.6% |
| 3 — legal-aware chunks | 83.9% | **5.4%** | 10.8% |
| 4 — full corpus | 87.5% | 6.2% | **6.2%** |

Misattribution is what legal-aware chunking fixes — 18.6% to 5.4%, a two-thirds reduction
from one change, and the direct measurement of the claim that a chunk must not cross a
section boundary. Fabrication is what retrieval fixes, falling monotonically at every stage.
Neither number is visible when the two are added together.

**Hosted model** (`openai/gpt-oss-120b`), all four stages complete. Stages 1 and 2 predate
questions added to the gold set later, so they cover 93 and 95 of 101; stages 3 and 4 cover
all 101:

| Stage | Retrieval recall | Citation precision | Answer hit rate | Excerpt validity | Refusal accuracy |
|---|---|---|---|---|---|
| 1 — LLM only | n/a | 17.9% | 24.0% | **0.0%** | 86.0% |
| 2 — naive chunks | 45.5% | 54.9% | 51.9% | **96.2%** | 66.3% |
| 3 — legal-aware chunks | 80.5% | **79.3%** | 80.5% | 90.9% | 84.2% |
| 4 — full corpus + offence lookup | **81.8%** | 72.9% | **83.1%** | 91.3% | **87.1%** |

**The stage 4 trade shows up on both models, which is what makes it a property of the
pipeline rather than of one model.** Adding the Penal Code and Schedule II costs citation
precision — 79.3% to 72.9% hosted, 66.3% to 59.1% local — because a thousand more chunks
compete for the same eight retrieval slots. What it buys is the same on both: offence
classification becomes answerable at all, and refusal accuracy rises (84.2% to 87.1% hosted,
88.1% to 90.1% local).

**Where the two models differ most is misattribution.** The local model quotes one section's
words under another's at every retrieval stage — 18.6%, 5.4%, 6.2% — and the hosted model
essentially never does: 0.8%, 0.0%, 0.0%. At stage 2 the windows that cause it are identical
between the tracks. Chunking creates the opportunity; whether a model takes it is the model's
property, and only running both shows which is which.

**The baseline is the control the rest of the table depends on.** On both models, stage 1
quotes from memory with no statutory text in front of it, and **every single quotation —
143 on the hosted model, 13 on the local one — is text that appears in no section of the
corpus.** Not one is real. That is the number every later stage is measured against, and it
is why the allowances described in [ADR 0011](docs/adr/0011-what-counts-as-a-verbatim-quotation.md)
can be read as a correction rather than a loosened threshold: they rescue none of it.

## Hosted stages 3 and 4

**Both complete**, each 101 of 101 with no errors: stage 4 on 14 September, stage 3 on 16
September.

Retrieval is identical between the tracks at each stage — same index, same offence lookup,
80.5% and 81.8% recall on both — so what separates the rows is the model:

| | Citation precision | Answer hit rate | Excerpt validity | Fabricated | Over-elided | Refusal accuracy |
|---|---|---|---|---|---|---|
| stage 3, local `qwen2.5:3b` | 66.3% | 63.6% | 83.9% | 10.8% | 0.0% | **88.1%** |
| stage 3, hosted `gpt-oss-120b` | **79.3%** | **80.5%** | **90.9%** | **0.6%** | 8.5% | 84.2% |
| stage 4, local | 59.1% | 61.0% | 87.5% | 6.2% | 0.0% | **90.1%** |
| stage 4, hosted | 72.9% | **83.1%** | **91.3%** | 1.9% | 6.2% | 87.1% |

By slice at stage 3 the gap is widest where a question needs more than one provision:
multi-section questions carry a correct citation 92% of the time on the hosted model against
58% on the local one, and Bangla questions 40% against 10%. The ambiguous slice is 0% on
both — neither model asks for the clarification those questions need, which is the clearest
remaining weakness in the system and is not a retrieval problem.

**Over-elision is a hosted habit.** 8.5% of its stage 3 quotations and 6.2% of its stage 4
ones are the cited section's own words, in the section's order, cut past the 20-character
floor — this one from stage 4, where "if the Magistrate" is the piece that falls under it:

> "if the Magistrate ... considers the charge to be groundless, he shall discharge the
> accused and record his reasons for so doing."

The local model does not produce one in any of its four runs. Rejecting them is
right — "shall" is not evidence — but they are not fabrications, and calling them that is
what the scorer used to do.

**The first scores were wrong, and were corrected before publication.** Scored as recorded,
stage 4 reported 11.2% fabrication and stage 3 reported 11.5%, both worse than hosted stage 2
while every other metric improved. Read one quotation at a time, 3 of stage 4's 18 and 1 of
stage 3's 19 were fabrications. The rest were a non-breaking hyphen the corpus never
contains, an elided piece ending on its own full stop, and a classifier that counted every
rejected elision as invented text. The correction and its effect on every run are in
[ADR 0011's amendment](docs/adr/0011-what-counts-as-a-verbatim-quotation.md#amendment-2026-09-14-two-artifacts-and-what-a-failed-elision-is).

**Not quite like-for-like, and why.** Every earlier RAG run on both tracks was recorded
before 2026-09-12 18:19, when the prompt gained the rule asking for short quotations. These
two used the current prompt. Retrieval and data are identical, so the hosted-against-local
gaps above are the model and that rule together, not the model alone.

**The 47 "banked" answers were not reusable.** Answers are cached under a key that includes
the prompt, and the prompt had changed since they were recorded. Checked across the whole
dataset without a model call, before anything was spent: 0 of 101 were reusable for either
stage. Both ran from nothing.

**What it cost.** Stage 4: 101 answers in 6 hours 21 minutes. Stage 3: 31 hours 12 minutes,
nearly all of it waiting — it began the moment stage 4 had drained the allowance. About 2,500
tokens an answer on average, because `gpt-oss-120b` reasons before it answers; one sampled
call spent 4,300. The allowance is a rolling 24-hour window rather than a daily reset, so
tokens return 24 hours after they are spent: roughly 80 answers fit in a burst, then about
three an hour until the next day's burst.

**Nothing partial is written, deliberately.** The harness refuses to emit a half-finished
sweep: the gold set is ordered, so stopping early biases whichever slices come last. Run with
`--wait-for-budget` it sleeps through a spent allowance and resumes from cache:

```bash
cd backend && uv run python -m app.evaluation.harness --stage 3 --provider groq --wait-for-budget
```

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

### 2026-09-12 — Incremental document update

**Objective.** Demonstrate that the corpus can gain, replace and lose documents without
rebuilding the index, and measure what each operation actually costs.

**Method.** Chunks carry a stable id and a hash of their text. An update re-derives the
chunk set every ingested source implies and compares it to the index: unchanged chunks
keep the vectors they already have, and only new or altered ones are embedded.

**Result.**

| Operation | Embedded | Reused | Time |
|---|---|---|---|
| Full build, Code only | 621 of 621 | — | 19.3 s |
| Add Schedule II | 376 of 997 | 62% | 14.0 s |
| Amend one section | 1 of 997 | 99.9% | under 0.1 s |

Amending section 61 — changing "twenty-four hours" to "forty-eight hours", as bdlaws
would publish after an amendment — re-embedded exactly one chunk, and the indexed text
changed accordingly. Reverting it re-embedded exactly one chunk again.

**A note on how this was demonstrated.** The intended demonstration was to add a real
related act, the Evidence Act 1872, live from bdlaws. The site became entirely
unreachable while this was being built — `http 000` after 100 seconds, including for
`act-print-75.html`, which had been fetched successfully the day before.

The demonstration was therefore rebuilt to use only local sources, which turned out to
be the better design. A demonstration of the update mechanism should not depend on a
third party being up, and a reviewer running it a week from now would otherwise see a
timeout rather than a result.

**Failure case examined.** The first run reported "100% reused" alongside "embedded 1 of
997". Both were produced by the same function, and the percentage was simply
996/997 rounded. A summary claiming nothing was re-embedded, printed next to a count
saying one chunk was, is the kind of small inconsistency that makes a reader reasonably
distrust every other number on the page. Proportions above 99.5% now render to one
decimal place whenever anything was embedded.

The same run also printed section 497 as the top result for "is theft a bailable
offence?", because the demo searched the raw index rather than going through the
offence lookup. That was accurate about the index and misleading about the system, so
the demo now shows both paths and says why each exists.

**Decision.** Deliverable §08.6 satisfied. The update path is the same code the corpus
uses in normal operation, not a demonstration script alongside it.

### 2026-09-12 — Adding the Penal Code, and the check ADR 0007 promised

**Objective.** Add a real related act through the production update path, and test
ADR 0007's stated risk: that general and special provisions on the same subject would
compete and degrade retrieval on core questions.

**Method.** The Penal Code, 1860 (act-11, 555 sections, 601 chunks) was fetched before
bdlaws became unreachable. It was added with `python -m app.retrieval.update`, and
retrieval-only evaluation was run before and after — no model in the loop, so any
change is attributable to the corpus.

**Result.** The addition cost only the new act's embeddings: **601 of 1598 chunks
embedded, 62% reused, 19.2 seconds**. The corpus went from 997 to 1598 chunks.

Retrieval did not degrade. It improved.

| Index | Chunks | R@1 | R@10 | direct_lookup R@10 |
|---|---|---|---|---|
| legal_aware (CrPC only) | 621 | 58.7% | 86.7% | 93.0% |
| + Schedule II + Penal Code | 1598 | **61.3%** | **89.3%** | **97.7%** |

The competition ADR 0007 anticipated did not materialise at this corpus size. That is a
measurement, not a guarantee — it says nothing about what happens at ten acts, and the
check is cheap enough to repeat on every addition.

**A bug this nearly caused.** `legal_aware` hardcoded every chunk's document as the
Code. Adding the Penal Code would have labelled all 601 of its sections as CrPC
sections, so "Penal Code section 302" — murder — would have been cited as CrPC section
302, and the citation validator would have confirmed it against the wrong statute.
Chunk ids collided for the same reason: two acts both have a section 302, so an
incremental update would have treated one as a modification of the other. Both are
fixed, and chunk ids now carry the document code.

**Two questions became answerable.** "What is the punishment for theft?" and "What is
the legal definition of murder?" were marked unanswerable pending the Penal Code, and
now resolve to Penal Code sections 379 and 300. Promoting them dropped the refusal
slice to 18.9% of the dataset, below the 20% floor a test enforces — a dataset weighted
toward answerable questions teaches a system to always answer. Six genuinely
out-of-scope questions were added rather than lowering the floor, covering the Evidence
Act, civil procedure, labour, company and narcotics law.

One of them is deliberately a near miss: "is a confession to a police officer
admissible against the accused?" Admissibility is Evidence Act section 25, but CrPC
sections 162 and 164 are about confessions and will retrieve well. The corpus must
decline rather than answer from 164, and nothing else in the dataset tests that.

### 2026-09-12 — Reading the failures instead of the rate

**Objective.** Stage 4 reported 65.6% excerpt validity — the metric that carries this
system's central claim, that a quoted excerpt is the section's own words. Rather than
record the number, read all 97 quotations it was computed from.

**Method.** Every quotation the checker rejected was printed beside the text of the
section it was attributed to, and classified by hand. Then each correction was isolated
by **re-scoring the same stored answers**, so nothing about the system changed and any
movement is a measurement defect rather than an improvement.

**Result.** Most of the failures were faithful quotations the check could not recognise,
for four distinct reasons, three in the checker and one in the corpus.

1. **Editorial apparatus.** bdlaws marks amended words with square brackets and words
   repealed out of a provision with `[* * *]` — 664 and 366 of them in the Code. Section
   200 reads `examine [upon oath the complainant ...]`. Quoting it without brackets, as
   any lawyer would, failed.
2. **Elision.** A quotation skipping a passage with an ellipsis was scored as invented.
3. **The label.** Each extract is introduced by a synthesised heading. Models copy it
   into the quotation. In stage 3, **20 of 98 quotations** did — one in five — and the
   words after the label were exact.
4. **A gap the ingester left.** Footnote markers sit between a word and the punctuation
   after it, so stripping them left `the Evidence Act, 1872 , section 24`. Twenty-seven
   of these reached the ingested Code. They are visible to anyone reading a quoted
   excerpt, and they made a faithful quotation of section 163 fail against its own text.

A fifth defect sat in the scorer. It resolved every citation against the Code of Criminal
Procedure, ignoring the document the citation claimed, so a Schedule II quotation about
theft was compared against Code section 379 — which is about appeals. The validation gate
had already been taught to resolve by document; the scorer had its own copy of the logic
and had not. Both now call one implementation.

**Same answers, corrected scorer.** Local model, `qwen2.5:3b-instruct`:

| Stage | Excerpt validity, before | after | matched as written | Citation existence |
|---|---|---|---|---|
| 1 — LLM only | 0.0% | **0.0%** | 0.0% | 91.4% |
| 2 — naive chunks | 54.4% | **57.1%** | 56.0% | 98.9% |
| 3 — legal-aware chunks | 40.8% | **61.2%** | 40.8% | 100.0% |
| 4 — full corpus | 65.6% | **80.4%** | 72.2% | 100.0% |

Hosted model, `openai/gpt-oss-120b`, re-scored from stored answers without spending any
budget:

| Stage | Excerpt validity, before | after | matched as written |
|---|---|---|---|
| 1 — LLM only | 0.0% | **0.0%** | 0.0% |
| 2 — naive chunks | 74.6% | **92.3%** | 75.4% |

A fourth allowance was added later, for the same reason and with the same
safeguard: a quotation that is verbatim for most of its length and drifts near the end is
displayed as the part that matched. A local model asked about section 54 returned 3,838
characters — the whole section — of which the first 3,328 were the statute word for word; it
had inserted one comma three thousand characters in, and the whole quotation was rejected
for it. The trimmed part has to be at least half of what was quoted, so a quotation that is
right for a clause and invented thereafter is not rescued by its opening.

**Why this is a correction and not a loosening.** Stage 1 is the control. It quotes from
memory with no text in front of it. Of its 15 quotations, the allowances rescue **zero** —
13 rejected outright, 2 citing sections that do not exist — on both models. Every
fabrication is still scored as a fabrication. A quotation consisting only of a marginal
note also still fails: the note is an editor's summary, and presenting one as law is the
failure this system exists to prevent.

Both rates are published. `excerpt_validity` counts quotations that verified after an
allowance; `excerpt_validity_unrepaired` counts only those that matched as written.
Anyone who disagrees with an allowance can read the stricter column. See
[ADR 0011](docs/adr/0011-what-counts-as-a-verbatim-quotation.md).

**What made this findable.** Not a test — every test passed throughout. The rate was
lower than the previous stage's and there was no story that explained it, which is the
only reason the quotations were read at all. Three of the four artefacts are invisible in
aggregate and obvious in ten minutes of reading individual failures.

**An infrastructure change this forced.** Re-scoring the hosted runs was nearly
impossible: their answers existed only in the response cache, under a key shape that
predated the fingerprint, and I had to search the prompt's git history to find them. Runs
now write `answers.jsonl` beside their scores, and `python -m app.evaluation.rescore`
re-derives the scores from it. A score is downstream of an answer, and correcting the
scorer should never mean paying a model again to re-measure text that has not changed.

### 2026-09-12 — Four stages on the corrected pipeline

> **Figures below are as scored on the day.** A later revision to the quotation
> checker — showing the verbatim part of an over-long quotation rather than
> rejecting it whole — raised excerpt validity at every stage. The current
> numbers are in [Results summary](#results-summary); every run was re-scored
> with `rescore --all`, which is what storing answers beside scores is for.
> `excerpt_validity_unrepaired` is unchanged, because no allowance touches it.

**Objective.** Re-run every stage after the scorer, the prompt and the extract rendering
were corrected, and separate what each change was responsible for.

**Method.** All four stages on `qwen2.5:3b-instruct`, 101 questions, same index family,
same gold set. Two things had changed since the previous sweep: the extract label is now
marked as a label with the statutory text fenced and the prompt says to quote only from
between the fences, and the scorer resolves each citation against the document it claims.
After the sweep every run — both models, all six — was re-scored by one scorer so the rows
compare with each other.

**Result.** Complete, 101 of 101 measured at every stage, zero errors:

| Stage | Recall | Citation precision | Answer hit rate | Excerpt validity | as written | Refusal accuracy |
|---|---|---|---|---|---|---|
| 1 — LLM only | n/a | 6.9% | 1.3% | 0.0% | 0.0% | 73.3% |
| 2 — naive chunks | 63.6% | 61.2% | 48.0% | 42.9% | 42.9% | 90.1% |
| 3 — legal-aware chunks | 80.5% | **66.3%** | **63.6%** | 77.4% | 67.7% | 88.1% |
| 4 — full corpus | **81.8%** | 59.1% | 61.0% | **81.2%** | 62.5% | **90.1%** |

**The prompt change did what it was for, and only there.** Stage 3's as-written excerpt
validity — quotations that matched with no allowance made — went from 40.8% to 67.7%. That
is the model no longer copying the extract's label into its quotations, which is what the
fencing and the prompt rule were for.

It did not help stage 2, and appears to have hurt it. Comparing the same stage across the
two sweeps:

| stage 2 | quotations | verified | wrong section | in no section |
|---|---|---|---|---|
| previous sweep | 91 | 57.1% | 17.6% | 25.3% |
| this sweep | 70 | 42.9% | 18.6% | **38.6%** |

The model quoted less often and invented more of what it did quote. The plausible reading is
that a stricter instruction pushes a 3B model toward paraphrase, and a paraphrase offered as
a quotation is a fabrication. **Two things changed between these sweeps** — the prompt and a
rebuilt index — so the cause is not isolated and is not claimed to be. What the comparison
does establish is that misattribution held steady at about 18% either way: it is a property
of naive chunking, not something a prompt or a retrieval improvement moves.

**A prediction that failed, and what it cost to find out.** The first explanation for stage
2's low excerpt validity was that its windows cross section boundaries. Tested per section —
does any window attributed to this section cross a boundary — the answer was no: 44% valid
for crossing sections against 42% for clean ones, indistinguishable. The hypothesis was
right and the test was wrong. The effect is per *window*, not per section, and 342 of 465
naive windows cross. Reading the failures individually showed it immediately:

> `"cy. 52. The officer or other person making any arrest under this Code may take from the
> person arrested any offensive weapons..."`

`cy.` is the tail of *decency* from section 51. The window starts mid-word, runs through
two boundaries, and the provision quoted is section 53, cited as 52. The model copied
exactly what it was shown.

**A check that came back negative, recorded because it nearly went in the other direction.**
A chunking change has no effect until the index is rebuilt, and the indexes were rebuilt
during this work — so part of what looks like a prompt improvement could have been a code
fix finally reaching the index. It was not. The incremental update's dry run reported 37 of
1598 chunks changed; had the index still held pre-refactor text, removing the inline heading
would have changed all 1222 act chunks. The index was already current, and the improvement
is attributable to the prompt and the rendering.

**Where stage 4 is worse.** Citation precision falls from 66.3% to 59.1% and answer hit rate
from 63.6% to 61.0% when the Penal Code and Schedule II join the corpus. Nearly a thousand
additional chunks compete for the same eight retrieval slots, and some Code sections that
were reaching the model no longer do. What is bought with that is the ability to answer
offence-classification questions at all, a further fall in fabrication (17.2% to 12.5%), and
the best refusal accuracy of any stage. Recorded as a trade rather than an improvement,
because that is what it is, and act-aware ranking is the obvious response to it.
