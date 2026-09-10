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

