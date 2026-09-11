# AI Usage

This project was developed with AI assistance. This document records which tools were used,
what was delegated to them, how the output was reviewed, and where AI suggestions were
rejected or corrected.

All work here has been reviewed and is understood well enough to explain in detail.

## Tools

| Tool | Model | Use |
|---|---|---|
| Claude Code | Claude Opus 5 | Source survey, architecture decisions, implementation, documentation |

## Provenance in the Git history

Commits produced with AI assistance carry a `Co-Authored-By: Claude Opus 5` trailer. This is
not decoration — it means the commit history itself is an accurate record of where assistance
was used, and can be audited with:

```bash
git log --format='%h %s' --grep='Co-Authored-By: Claude' 
```

## What was delegated

**Source investigation.** Inspecting `bdlaws.minlaw.gov.bd` to establish how Bangladesh
legislation is published — URL structure, section boundaries, hierarchy markers, and how
amendments are represented. Findings in [DATA_SOURCE.md](DATA_SOURCE.md).

**Architecture decisions.** Drafting the ADRs in [docs/adr/](docs/adr/). The decisions were
reviewed and accepted individually; one was subsequently reversed (see below).

**Implementation.** Backend scaffolding, the provider abstraction, tests.

**Documentation.** This file, the README, the experiment log structure.

## Review process

Every generated file was read before committing. Code is not committed unless its tests
pass — the backend scaffold was committed only after `pytest` ran green on Python 3.12.13.

Claims about the source corpus are not accepted from the model on assertion. Every structural
claim in [DATA_SOURCE.md](DATA_SOURCE.md) was established by direct inspection of the live
site and is stated with the evidence that produced it, including the specific URLs examined.
Where a number was not verified — the exact count of legal sections, early on — it was
recorded as unverified rather than estimated.

## Rejected and corrected suggestions

This section is the point of the document. It is appended to as the project continues.

### 1. Per-section crawl with title-based reassembly — rejected on evidence

**What the assistant proposed.** ADR 0002: a two-pass crawl of all 594 per-section URLs,
extracting section numbers from each page's `<title>` element and reassembling fragmented
pages into whole sections, with continuation pages inheriting the number of the most recent
numbered page in table-of-contents order.

**Why it was wrong.** Not incorrect on its own terms — the reassembly logic would have
worked. It solved a problem that did not need to exist. The assistant surveyed the
per-section endpoints, found them fragmented, and designed around the fragmentation instead
of checking whether a better endpoint existed.

**How it was caught.** By being pointed at `act-details-75.html` directly, which turned out
to serve the entire act as a single document with section grouping intact.

**Correction.** ADR 0002 superseded by [ADR 0005](docs/adr/0005-ingest-from-single-document-print-view.md).
Ingestion now uses one request rather than 594, and the number-inheritance heuristic was
deleted before it was ever written. ADR 0002 was marked superseded rather than rewritten, so
the reversal stays visible.

**Lesson recorded.** Survey the full surface of a data source before designing around any
part of it. An AI assistant investigating a source will design confidently around whatever
it happened to look at first, and the resulting design will look well-reasoned because it
is well-reasoned — about the wrong subset.

### 2. Marginal-note fragmentation — caught before it reached code

**What nearly happened.** The obvious ingestion design, and the one an assistant produces
without investigation, is one URL to one document to one chunk. Against this source that
silently shreds sections and produces citations naming a marginal note with no section
number.

**How it was caught.** Investigating the source structure before writing the ingestion
pipeline, rather than writing the pipeline and debugging its output.

**Why it is recorded here.** It is the failure mode this project is most exposed to. A
citation-grounded legal assistant that cites confidently and wrongly is worse than one that
declines to answer, and this class of bug produces exactly that.

### 3. Web framework adopted by default, not by choice — corrected

**What happened.** The initial scaffold used FastAPI because it is the assistant's default
for a Python API. No alternatives were examined and no rationale was recorded, so a
technology choice the brief explicitly asks about was in the repository as an unexamined
habit.

**How it was caught.** By being asked directly whether a better Python framework existed.

**Correction.** [ADR 0008](docs/adr/0008-web-framework-choice.md) now examines Litestar,
Django Ninja, Flask/Quart and three others against the system's actual requirements. The
decision did not change — FastAPI is retained — but it is now a decision rather than a
default, with the rejected alternatives and the reason for each recorded, including the one
case (Django Ninja, if corpus administration grows) that would justify revisiting it.

**Lesson recorded.** An AI assistant supplies defaults fluently and rarely flags that a
default was applied. The output looks identical whether a choice was reasoned or reflexive,
which makes unexamined defaults hard to spot by reading the code. Where the brief asks for
technology *choices*, the alternatives have to be written down even when the default turns
out to be right.

### 4. Parser written from assumed structure, corrected by running it

**What the assistant proposed.** A section detector based on the layout's apparent
regularity — match a leading section number, treat unnumbered units as continuations.

**Why it was wrong.** It was right about the layout and wrong about identity. Five
source conventions break the mapping from unit to section, and the first version lost
133 sections including section 54, while reporting a section count plausible enough to
accept without checking.

**How it was caught.** By comparing the full recovered section list against the source
rather than inspecting a few sections. Every bug found in this pass was found by
checking output against the whole document; none were visible in a sample.

**Correction.** Four iterations, documented in EXPERIMENTS.md with the count at each
stage, and a test per convention.

**Lesson recorded.** A parser that produces well-formed output is not a parser that
produces correct output, and an assistant will report success on the former. For a
citation-grounded system the distinction is the whole product: a corpus with
mislabelled sections retrieves fluently and cites confidently, and no retrieval metric
detects it, because retrieval succeeded — against the wrong text.

### 5. Model identifiers hardcoded from memory — corrected against the live catalogue

**What the assistant proposed.** Provider defaults naming `llama-3.3-70b-versatile` for
chat and `meta-llama/llama-4-scout-17b-16e-instruct` for vision.

**Why it was wrong.** Neither exists on the account's catalogue. The failure mode is
particularly misleading: authentication succeeds, `/api/meta` reports a model name, and
every actual request returns an error — which reads as a credential problem and is not
one. Diagnosis went to the API key first, and the key was fine.

**How it was caught.** By querying `models.list()` to separate an auth failure from a
model-availability failure, rather than continuing to investigate the credential.

**Correction.** Defaults now come from the live catalogue (`openai/gpt-oss-120b` for
chat, `whisper-large-v3` for transcription, both verified present), and
`python -m app.llm.models` prints the catalogue and flags any configured model missing
from it. The catalogue offers no vision-capable model, so `groq_vision_model` is unset
and the provider declares no vision capability rather than advertising one that fails
at call time.

**Lesson recorded.** Model identifiers change without notice and differ between
accounts and tiers. They are exactly the kind of detail an assistant produces
confidently from training data, and exactly the kind that cannot be verified by reading
the code — only by asking the provider.

### 6. A test that passed for the wrong reason

**What happened.** A test asserting the service boots with a missing API key passed
only because no `.env` existed in the repository. The moment a real `.env` was created,
the test began exercising a configured provider instead of a missing one — and failed,
which is how it was noticed. Had it been written to be lenient, it would have gone on
passing while testing nothing.

**Correction.** `tests/conftest.py` runs the suite from a directory with no `.env` and
clears the settings and provider caches around each test, so behaviour no longer
depends on the developer's environment.

**Lesson recorded.** Green tests are evidence only if they can fail. This one depended
on the absence of a file that the setup instructions tell every developer to create.

### 7. A flag that was accepted, documented, and did nothing

**What happened.** A patch added `--wait-for-budget` to the evaluation harness so an
overnight sweep would sleep through the provider's daily limit instead of stopping.
The patch applied the change that *registers* the flag and silently failed to apply
the change that *reads* it, because the surrounding code had been rewritten in an
earlier session and no longer matched the text being replaced.

The flag then appeared in `--help`. argparse accepted it without complaint. Lint
passed. The patch script printed "patched". Every signal available short of running
it said the feature worked.

It did not. A long sweep launched with the flag stopped at the first daily limit,
having spent hours of budget to produce nothing.

**How it was caught.** By reading the run's output afterwards and noticing it had
printed the stop-and-explain panel rather than the sleep-and-resume message. Not by
any check performed at the time of writing.

**Correction.** The flag is wired through `run_stage`, and `tests/test_harness_wiring.py`
asserts that every CLI flag *reaches* `run_stage`, that `run_stage` accepts everything
`main` passes, and that the body actually consults the parameter rather than merely
declaring it.

**Lesson recorded.** String-replacement patching fails open. When the anchor text has
moved, the edit vanishes and the surrounding code still compiles, still lints, and
still starts — so the usual signals all report success. The failure is only visible in
behaviour. Anything edited by pattern-matching against existing source needs a test
that exercises the path, not a check that the file parses.

### 8. Code written for one act, silently assuming there would only ever be one

**What happened.** The chunker set every chunk's document to the Code of Criminal
Procedure, and built chunk ids from the section number alone. Both were correct while
the corpus held one act, and both were wrong the moment it held two — but nothing in
the code said "this assumes a single act", and nothing failed while that was true.

Adding the Penal Code would have labelled all 601 of its sections as CrPC sections.
Penal Code section 302 is murder and CrPC section 302 is not, so the citation
validator — the component whose entire job is catching wrong citations — would have
confirmed it against the wrong statute. Chunk ids collided for the same reason: both
acts have a section 302, so an incremental update would have treated one as a
modification of the other and quietly replaced it.

**How it was caught.** By adding a second act. Not by review, not by tests — every
test passed throughout, because every test used one act.

**Correction.** Chunks carry a document code derived from the act, ids include it, and
citations are validated against the document they name.

**Lesson recorded.** An assistant writes for the case in front of it and rarely marks
where it has assumed away a dimension. The assumption is invisible in the result: the
code is clean, the tests pass, and the defect only exists in a situation that has not
happened yet. The tell is a field that could vary but is written as a constant —
`document=CRPC` in a function that takes an act as its argument.

### 9. A test that found a 500 the design intended to be a 503

**What happened.** Writing a test for "asking about a document that no longer exists",
the failure was not the 404 under test but a `RuntimeError` from constructing the
model provider — which escaped the handler as an unexplained 500.

The route already caught `CorpusUnavailable` and returned 503 with the fix, and `/meta`
already degraded rather than failing on a missing credential. This path had simply not
been given the same treatment, and no existing test exercised it.

**Correction.** Provider construction failures return 503 with the reason. Separately,
the uploaded document is now resolved before the corpus loads, so a missing document
reports the right problem whatever else is misconfigured — which also took that test
from 97 seconds to 2.

**Lesson recorded.** The bug was found by a test aimed at something else entirely.
Tests written for one behaviour routinely walk through code paths nobody chose to
examine, which is an argument for writing them even where the behaviour seems obvious
enough not to need one.


### 10. Two copies of one rule, and only one of them was fixed

**What happened.** Citations are checked in two places: the validation gate, which
decides what a user is shown, and the evaluation scorer, which decides what the
experiment log reports. Both had to answer "does this quotation appear in the section
it cites", and each had its own implementation of it.

When the corpus grew past a single act, the gate was taught to resolve a citation
against the document it claims — Penal Code section 300 against the Penal Code, a
Schedule II row against Schedule II. The scorer was not. It went on resolving every
citation against the Code of Criminal Procedure, so a faithful Schedule II quotation
about theft was compared against Code section 379, which is about appeals.

The effect was quiet and pointed in the wrong direction: it understated the system on
exactly the offence questions stage 4 was built to answer, and it reported citations as
hallucinated when the model had cited correctly into a document the scorer declined to
look in.

**How it was caught.** By not believing a rate. Stage 4 reported 65.6% excerpt validity
and 99.0% citation existence, so I read all 97 quotations individually instead of
recording the number. Most of the failures were quotations a lawyer would call
faithful.

**Correction.** One implementation, in `app/qa/quoting.py`, used by both. The
duplication is the actual defect; the divergence was only its symptom.

**Lesson recorded.** I wrote both copies, and writing the second one is where the
assistant's habits show: asked to score answers, it implements scoring, and it
implements the comparison it needs rather than looking for the one already written
twenty lines away in another module. Nothing flags it. Both copies are correct on the
day they are written, the tests pass on both, and they only disagree later, when one is
changed for a reason that did not obviously apply to the other.

The tell is a rule stated in prose in two files. `validation.py` and `metrics.py` each
opened with a docstring promising that a quotation is checked verbatim against its
section. That sentence appearing twice was the warning, and I wrote it twice without
noticing.

### 11. I dry-ran one of three, then applied to all three

**What happened.** A small ingestion fix meant the indexes needed updating. I ran
`python -m app.retrieval.update --dry-run` against `legal_aware_schedule`, read a
sensible result — 37 of 1598 chunks changed — and then applied the update to all three
indexes in a loop.

The command derives its chunk set from a function that always builds legal-aware chunks
over every ingested act plus Schedule II, regardless of which index it was pointed at.
On `legal_aware_schedule` that is correct, which is why the dry run looked fine. On the
other two it is a replacement. The naive-chunk index went from 465 chunks to 1598, and
the legal-aware CrPC-only index went from 621 to 1598. Both became copies of the stage 4
corpus.

Stages 2 and 3 exist to measure one variable: chunking strategy. Their indexes had just
become identical. The comparison would have run, produced numbers, and shown a smaller
difference than before — which I would have had to explain, and could have explained
plausibly and wrongly.

**How it was caught.** The output said so — `1598 added, 0 changed, 0 unchanged, 465
removed` — and I read it. It was caught in the second between running the command and
reading its result, which is not a system, and the reason there is now a guard.

**Correction.** The update reads the index's own chunking strategy and documents off
its chunks rather than assuming, and refuses when an operation would add and remove more
than a quarter of the index, naming the rebuild command instead. Both indexes were
rebuilt and verified at their original sizes.

**Lesson recorded.** Two failures stacked, and only one of them was the assistant's.

Mine: a dry run on one of three targets is not a dry run. I generalised a safe result
across targets that were not the same, which is the identical shape of reasoning that
put `document=CRPC` in a function taking an act as its argument (entry 8) — assuming a
dimension is constant because in the case in front of me it was.

The code's: a command whose destructive scope is not derived from its argument. The
`--index` flag chose what to overwrite but not what to overwrite it with. A flag that
selects a target without selecting the target's definition is a loaded gun, and the
dry-run made it look safe.

The failure was silent in the only way that matters here: nothing errored, the indexes
were valid, the tests passed, and the evaluation would have reported confidently on a
comparison that no longer existed.

### 12. Three features that existed only in the documentation

**What happened.** Checking the README against the code rather than against my memory of
writing it turned up three capabilities described as though built, and not built:
hybrid BM25 + dense retrieval fused by reciprocal rank, named in two technology tables
and listed as stage 4; a faithfulness metric scored by an LLM judge against a rubric;
and streaming answers in the frontend.

Each was written early, in the design documents, in the present tense — the tense
design documents are written in. The build then went a different way for reasons that
were good, and the sentence describing the original plan stayed exactly where it was.
Stage 4 became the full corpus plus structured offence lookup, which answers the
question BM25 was aimed at more directly. Streaming is not merely absent but impossible
here, because the citation gate must see a complete answer before any of it is shown.

**How it was caught.** By grepping the documentation for its own claims and looking for
the implementation of each, rather than re-reading the prose. Re-reading it had not
worked: I had read that technology table several times while editing rows next to those
ones.

**Correction.** All three corrected in place, with the reasoning for the change recorded
where the claim used to be, and the dropped plan listed as untried rather than quietly
deleted.

**Lesson recorded.** This is the assistant failure mode with the longest fuse. Writing an
architecture document before the code is the right order, and an assistant writes such a
document fluently and in the present tense. Every later edit is local — a row here, a
paragraph there — and nothing in the editing process ever asks whether the surrounding
sentences are still true. The result reads as a description and functions as a wish.

The tell is tense and specificity together: a design document that says what the system
*does*, in detail, about a part nobody has pointed at in weeks. The check is mechanical
and takes minutes — grep the docs for each capability claimed, then grep the source for
it — and it is worth running before anyone else reads the repository, because the cost
of being caught overstating is not proportional to the size of the overstatement.
