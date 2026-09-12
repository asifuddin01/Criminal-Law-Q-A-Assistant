# Criminal Law Q&A Assistant

A source-grounded question-answering assistant for Bangladesh criminal law, built on the
Code of Criminal Procedure, 1898 (Act No. V of 1898) together with its amendments, its
schedules, and the related legislation the Code depends on.

Every answer is grounded in retrieved statutory text and carries section-level citations with
verbatim source excerpts. Where the corpus does not support a confident answer, the system
says so rather than producing one.

> **This system provides legal information, not legal advice.** It is not a substitute for a
> qualified advocate. Statutory text may have been amended after the corpus snapshot date,
> and retrieval may be incomplete. Verify against the official text published by the Ministry
> of Law, Justice and Parliamentary Affairs before relying on it.

## Status

**Live demo: [huggingface.co/spaces/asifuddin01/criminal-law-qa-bangladesh](https://huggingface.co/spaces/asifuddin01/criminal-law-qa-bangladesh)**

Complete and measured end to end on the local model; the hosted model has completed stages 1
and 2 and is rate-limited beyond that. This table is the honest state of the repository, not
a roadmap.

| Component | State |
|---|---|
| Architecture decisions | Recorded — [docs/adr/](docs/adr/) |
| Source survey | Complete — [DATA_SOURCE.md](DATA_SOURCE.md) |
| Evaluation methodology | Defined — [eval/README.md](eval/README.md) |
| Backend service, provider abstraction | Working, tested, connected to Groq |
| Ingestion pipeline | Parser working, tested — 522 sections, 599 amendments |
| Retrieval and generation | Complete — four stages measured on the local model |
| Hosted stages 3–4 | **In progress**, rate-limited — 47 of 101 answers banked, resumes from cache |
| Corpus | CrPC (522 sections), Schedule II (376 offence rows), Penal Code (555 sections) |
| Evaluation dataset | Built — 101 questions, all labels verified against fetched text |
| Frontend | Working — text, speech, image and document input; verified citations |
| Speech input | Working — `whisper-large-v3`, English and Bangla |
| Image input | Working — local OCR (tesseract, English + Bengali) |
| Document upload | Working — PDF and text, never treated as law |
| Amendment provenance | Working — every citation carries how and when the section changed |
| Deployment | **Live** — [Hugging Face Space](https://huggingface.co/spaces/asifuddin01/criminal-law-qa-bangladesh) |

## What was asked for, and what this does

Everything the brief required, including all three optional inputs.

| Required | Where it is |
|---|---|
| Q&A over a Bangladeshi legal corpus | CrPC 1898, its Schedule II, and the Penal Code 1860 |
| Answers grounded in retrieved text | Nothing is answered without retrieval; stage 1 exists to show the difference |
| Section-level citations | With verbatim excerpts, each checked against the source before display |
| Refuse when unsupported | A first-class outcome with its own metric — 90.1% refusal accuracy at stage 4 |
| Evaluation | 101 questions, six runs, one scorer over all of them |
| Documentation of approach | This file, [EXPERIMENTS.md](EXPERIMENTS.md), 11 [ADRs](docs/adr/), [AI_USAGE.md](AI_USAGE.md) |
| *Optional:* image input | tesseract OCR, English + Bengali |
| *Optional:* speech input | `whisper-large-v3`, English and Bangla |
| *Optional:* document upload | PDF and text, never treated as law |
| *Optional:* demo video **or** deployment | [Live Space](https://huggingface.co/spaces/asifuddin01/criminal-law-qa-bangladesh) |

### Beyond the brief

Each of these exists because something measurable went wrong without it.

| Addition | Why |
|---|---|
| Staged evaluation, one variable per stage | A number only means something against the stage before it. |
| LLM-only baseline as a control | 143 quotations, 143 fabricated — that is what the citation check is worth. |
| Misattribution told apart from fabrication | Real text under the wrong section is a chunking bug; invented text is a model bug. |
| Two excerpt-validity rates published | Publishing the strict one means nobody has to trust my allowances. |
| Structured Schedule II lookup | "Is theft bailable?" embeds near the sections *about* bail; the row that answers it ranks nowhere. |
| Document roles ([ADR 0006](docs/adr/0006-document-roles-separate-operative-law-from-amending-instruments.md)) | An amending act's text is a diff, not a provision — it must never answer as law. |
| Amendment provenance on every citation | Section 54 was substituted in force from 10 August 2025; the current wording does not say so. |
| Incremental index updates | A corpus you must rebuild in full is a corpus nobody updates. |
| Bangla translation, excerpts left in English | A translated "verbatim quote" is no longer verbatim. |
| Rate-limit handling that waits or switches | A half-finished sweep biases whichever slices come last and still looks like a result. |
| [`rescore`](backend/app/evaluation/rescore.py) | Correcting the scorer should not cost a hosted budget to re-measure text that has not changed. |
| Generated screenshots | A screenshot nobody can reproduce is a claim about a version that no longer exists. |

## What it looks like

Screenshots are generated by driving the running application
(`npm run screenshots`), not pasted, so they can be regenerated whenever the
interface changes.

**A Bangla question, answered and translated, with every citation verified**

![Bangla question with a translated answer and four verified citations](docs/screenshots/04-translated-to-bangla.png)

The answer is translated on demand; the statutory excerpts stay in English, because
each is shown with a claim that it appears verbatim in the source and a link to check
it. Four citations, all verified, with the part and chapter each sits under.

**Every citation carries how and when the section changed**

![Section 54 with its amendment history, linking to the amending act](docs/screenshots/05-amendment-provenance.png)

Section 54 reads as it does because Act XI of 2026 substituted it, with effect from 10
August 2025. The current wording does not say that, and whether this section governs a
matter depends on when the matter arose. Citations group by section — three verified
excerpts from section 54 are three pieces of evidence for one provision, not three
provisions.

**An English answer with its citations checked**

![An English answer with verified citations](docs/screenshots/02-answer-verified-citations.png)

**The same question in Bangla, answered from the English corpus**

![A Bangla question answered from the English corpus](docs/screenshots/03-bangla-question-english-answer.png)

**Landing state**

![Landing state showing the legal-information disclaimer](docs/screenshots/01-landing.png)

## Architecture

Full diagrams and the data model: **[docs/architecture.md](docs/architecture.md)**.

Two pipelines meet at the index. Ingestion parses statutory sources into sections, amendment
records and schedule rows. Query normalizes every input modality to text, retrieves under a
role filter, generates, and then passes the answer through a deterministic citation gate that
can refuse it.

Three decisions shape most of the design:

**Offence classification is looked up, not retrieved.** "Is theft a bailable
offence?" embeds closest to the sections *about* bail — 496 and 497 — while the row
that decides it, Penal Code section 379 in Schedule II, ranks nowhere. Retrieval would
hand the model the general bail provisions and get a fluent, correctly cited, wrong
answer. Questions naming an offence therefore get that offence's Schedule II row placed
in front of the model directly.

**The section is the unit of citation.** Chunks never cross section boundaries, because a
citation that cannot name a section is not verifiable.
([ADR 0002](docs/adr/0002-reassemble-pages-into-legal-sections.md),
[0005](docs/adr/0005-ingest-from-single-document-print-view.md))

**Documents carry a role, and only operative law is retrievable as law.** An amending act's
text is a diff, not a provision. Indexing it flat alongside the Code lets a question about
what a section provides retrieve a 1976 ordinance's instruction to delete a word — genuine
text, resolving citation, wrong answer. The role is inferred from the document's own title;
the update path skips a non-operative act and names it, and `build` refuses one outright.
([ADR 0006](docs/adr/0006-document-roles-separate-operative-law-from-amending-instruments.md))

**A section's current wording is not the whole answer.** Every citation carries the
amendments that produced it — what changed, under which act, and from what date — because a
provision substituted with effect from a date after the events being asked about is the
wrong provision for those events, and nothing in the text says so. Section 54 comes back
noting that it was substituted by Act XI of 2026 with effect from 10 August 2025.

**Modality is erased at the API boundary.** Speech, image and text converge on
`(question_text, attached_documents, language)` before retrieval, so one evaluation harness
covers every input path.
([ADR 0004](docs/adr/0004-normalize-input-modalities-at-the-boundary.md))

### Technology

| Layer | Choice |
|---|---|
| Backend | FastAPI, Python 3.12 ([why](docs/adr/0008-web-framework-choice.md)) |
| Index | Exact in-process NumPy search ([why](docs/adr/0009-exact-in-process-vector-search.md)) |
| Frontend | Next.js |
| Generation | Groq `openai/gpt-oss-120b`, Ollama `qwen2.5:3b-instruct` fallback |
| Speech | Groq `whisper-large-v3` (English and Bangla) |
| Image | tesseract OCR, local (`eng+ben`) |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (ONNX) |
| Retrieval | Dense (exact, in-process) plus direct offence lookup |

Groq and Ollama both expose an OpenAI-compatible API, so one client implementation serves
both, and one credential covers generation and transcription. Providers declare
capabilities from what is actually configured: an Ollama deployment reports text-only,
and the interface hides inputs it cannot serve rather than offering controls that fail
on use.

Model identifiers are verified against the live catalogue rather than assumed —
`python -m app.llm.models` prints it and flags anything configured but missing. The
current Groq catalogue offers **no vision-capable model**, so vision is not declared and
image input needs a separate path; see [Limitations](#limitations).

Retrieval choices are provisional. They are settled by measurement in
[EXPERIMENTS.md](EXPERIMENTS.md), not by assertion here.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync --all-groups
cp .env.example .env
```

Set `GROQ_API_KEY` in `backend/.env` from [console.groq.com/keys](https://console.groq.com/keys).

To run entirely locally instead, set `LLM_PROVIDER=ollama` and pull the model:

```bash
ollama pull qwen2.5:3b-instruct
```

Ingest the corpus and build the retrieval index:

```bash
cd backend && uv run python -m app.ingest && uv run python -m app.retrieval.build --strategy legal_aware
```

Run the API:

```bash
cd backend && uv run uvicorn app.main:app --port 8010 --reload
```

- Interactive API docs: `http://localhost:8010/docs`
- Liveness: `GET /api/health` — deliberately does not touch the model provider
- Capabilities: `GET /api/meta?probe=true` — active provider and what it supports
- Ask: `POST /api/ask` with `{"question": "...", "language": "en"}`

Run the web client, in a second terminal:

```bash
cd frontend && npm install && npm run dev
```

Then open `http://localhost:3000`.

Tests:

```bash
cd backend && uv run pytest
```

Useful checks:

```bash
cd backend && uv run python -m app.llm.models
```

prints the provider's live model catalogue and flags anything configured but missing —
model identifiers differ between accounts and a stale one fails every request while
looking like a credential problem.

## Deploying

The frontend exports to static files served by the API process, so a deployment is one
container on one port. Steps, limits and the local `docker run`:
**[docs/DEPLOY.md](docs/DEPLOY.md)**.

```bash
./deploy/push-to-space.sh <hf-username> <space-name>
```

The API key goes in the host's own secrets page, never in the repository.

Docker Spaces, and on some accounts CPU-basic hardware, are gated behind a paid tier, so the
Space runs under the `gradio` SDK on ZeroGPU hardware — which allocates a GPU only inside
`@spaces.GPU` calls, and this application never makes one — which serves this project's own FastAPI application rather than a Gradio
interface, keeping the real frontend. A working Gradio interface onto the same pipeline is
mounted at `/gradio/` as a hedge, because running FastAPI that way is not a documented
pattern. The `Dockerfile` is still there and is still the better option wherever Docker
Spaces are available; it is built and verified for `linux/amd64`.

Cold start is 21 seconds, down from 59 before Schedule II was precomputed ahead of time:
81% of the original startup was re-parsing a 161-page PDF that never changes, on every wake
of a Space that sleeps when idle.

## Data ingestion and update

Sources, structure and provenance: **[DATA_SOURCE.md](DATA_SOURCE.md)**.

The corpus comes from `bdlaws.minlaw.gov.bd`, published by the Legislative and Parliamentary
Affairs Division. Three source shapes:

| Shape | Endpoint | Handling |
|---|---|---|
| Whole act | `act-print-<id>.html` | One request per act. Segmented by section marker; footnotes parsed into amendment records. CrPC and the Penal Code are ingested |
| Schedule | `upload/act/…Schedule-II.pdf` | 161-page PDF, extracted into 376 structured offence rows |
| Amending acts | Individual acts | Ingested with role `amending`, excluded from retrieval as law |

Membership follows a stated criterion rather than intuition: an act is in scope if CrPC
incorporates it by normative reference, or if it displaces CrPC procedure via a non-obstante
clause ([ADR 0007](docs/adr/0007-inclusion-criterion-for-related-laws.md)).

**Updating.** The index converges on whatever sources are present in `data/raw`, so adding
an act, replacing one with a newer consolidation, and removing one are the same operation:

```bash
cd backend && uv run python -m app.retrieval.update --index legal_aware_schedule --dry-run
cd backend && uv run python -m app.retrieval.update --index legal_aware_schedule
```

Chunks are matched on a stable id and compared on a hash of their text, so only new or
altered chunks are embedded. A source republished with one provision amended re-embeds one
provision.

Name the index every time, and dry-run the one you are about to change rather than a
sibling. The update reads that index's own chunking strategy and document set off its
chunks — `naive_fixed_size` over the Code alone stays that, and is not converged onto the
full corpus because another index holds it. An operation that would add and remove more
than a quarter of an index is refused as a rebuild in disguise, since the runs already
recorded against an index stop being comparable the moment it changes shape underneath
them.

**Demonstration** ([transcript](docs/incremental-update-demo.txt)):

```bash
cd backend && uv run python -m app.retrieval.demo
```

| Operation | Embedded | Reused | Time |
|---|---|---|---|
| Full build, Code only | 621 of 621 | — | 19.3 s |
| Add Schedule II (376 rows) | 376 of 997 | 62% | 14.0 s |
| **Add the Penal Code (601 sections)** | **601 of 1598** | **62%** | **19.2 s** |
| Amend one section | **1 of 997** | **99.9%** | < 0.1 s |

The Penal Code row is a real addition through the production CLI, not a simulation. The
corpus went from 997 to 1598 chunks and the existing 997 kept the vectors they had.

Each addition is followed by an evaluation run, so an act that degrades retrieval on core
CrPC questions is detected rather than presumed harmless.

## Evaluation

Metrics, dataset schema and construction protocol: **[eval/README.md](eval/README.md)**.

The same dataset runs after every stage, so each change is attributable to a movement in a
number and a change that moves nothing is recorded as such. Every reported metric is
deterministic — no model is asked whether another model was honest. A faithfulness metric
scored by an LLM judge was specified early and deliberately not built; the reasoning, and
the gap it leaves, are in [eval/README.md](eval/README.md).

The dataset is stratified — direct lookup, multi-section, amended provisions, unanswerable,
ambiguous, Bangla. The unanswerable and ambiguous slices are not padding: a system tuned only
on answerable questions reliably learns to always answer.

Gold section labels are verified against fetched act text, never recalled. A wrong gold label
penalises correct retrieval and rewards incorrect retrieval, invisibly.

## Experiments and results

Running log with hypotheses, configurations, results and decisions:
**[EXPERIMENTS.md](EXPERIMENTS.md)**. Charts and the full table:
[eval/runs/charts/](eval/runs/charts/).

Four stages, each adding exactly one thing to the one before, measured on the same frozen
gold set so any movement is attributable:

| Stage | What changes |
|---|---|
| 1 — LLM only | No retrieval. Establishes what the model invents unaided. |
| 2 — naive chunks | Dense retrieval over fixed-size windows that ignore section boundaries. |
| 3 — legal-aware chunks | The same pipeline, chunked on the section — the unit of citation. |
| 4 — full corpus | Schedule II and the Penal Code added, plus structured offence lookup. |

The stage 1 baseline is not a formality. It is the control that makes the excerpt check
meaningful: quoting from memory with no text in front of it, **not one of its quotations is
real**, on either model. Every later stage is measured against that.

Complete on the local model, 101 of 101 questions measured at every stage, one scorer over
every run:

| Stage | Retrieval recall | Citation precision | Answer hit rate | Excerpt validity | Refusal accuracy |
|---|---|---|---|---|---|
| 1 — LLM only | n/a | 6.9% | 1.3% | **0.0%** | 73.3% |
| 2 — naive chunks | 63.6% | 61.2% | 48.0% | 42.9% | 90.1% |
| 3 — legal-aware chunks | 80.5% | **66.3%** | **63.6%** | 77.4% | 88.1% |
| 4 — full corpus + offence lookup | **81.8%** | 59.1% | 61.0% | **81.2%** | **90.1%** |

![Evaluation metrics by stage](eval/runs/charts/metric-progression-qwen2-5-3b-instruct.png)

A quotation that fails is two different failures, and they have opposite fixes. Real
statutory text quoted under the wrong section is a chunking defect — a window that crosses a
section boundary contains another section's words, and the model quotes it honestly. Text
found in no section at all is the model writing law. Added together they hide each other:

![Fabrication and misattribution by stage](eval/runs/charts/fabrication-qwen2-5-3b-instruct.png)

| Stage | Verified | Real text, wrong section | In no section at all |
|---|---|---|---|
| 1 — LLM only | 0.0% | 0.0% | **100.0%** |
| 2 — naive chunks | 42.9% | **18.6%** | 38.6% |
| 3 — legal-aware chunks | 77.4% | **5.4%** | 17.2% |
| 4 — full corpus | 81.2% | 6.2% | **12.5%** |

Misattribution is what chunking on section boundaries fixes: 18.6% to 5.4%, from that one
change. Fabrication is what retrieval fixes, falling at every stage from 100%.

Stage 4 is recorded as a trade, not an improvement. Citation precision falls — a thousand
more chunks compete for the same eight retrieval slots — and what is bought is the ability
to answer offence-classification questions at all, the lowest fabrication rate of any stage,
and the best refusal accuracy. Act-aware ranking is the obvious response and is not built.

The hosted model (`openai/gpt-oss-120b`) has completed stages 1 and 2, quoting far more
faithfully (92.3% excerpt validity against 42.9% at the same stage) and refusing far less
readily.

**Hosted stages 3 and 4 are in progress, paced by a free-tier daily token budget** — 47 of
101 answers are banked and each attempt resumes from cache rather than restarting. The
harness deliberately writes nothing for a partial sweep, because the gold set is ordered and
stopping early biases whichever slices come last. The four-stage conclusions do not depend on
it: that progression is measured end-to-end on the local model, where the model is constant
and every movement is attributable to the pipeline. Detail and the resume command are in
[EXPERIMENTS.md](EXPERIMENTS.md#hosted-stages-3-and-4-in-progress).

## Limitations

Stated now rather than discovered later.

**No point-in-time reconstruction.** The system reports when a provision changed, under
which act and from what date, and links the amending act — but it does not reconstruct the
text as it stood on a past date. bdlaws publishes
only the current consolidation, and the footnotes do not always preserve replaced wording in
full. Approximating this would be worse than declining it.

**English corpus.** Bangla questions are supported against English statutory text. The Bangla
texts on bdlaws are not yet ingested, so answers and quoted excerpts are in English.

**Translation quality depends on the model, and the local fallback is not good
enough for it.** Answers can be translated into Bangla on demand. The hosted model
produces sound legal Bangla; `qwen2.5:3b-instruct` produces text a Bangla reader would
find wrong in places, inventing phrases that are not Bengali legal terms. The feature
is therefore usable on the hosted provider and should be treated as unavailable on the
local one. Statutory excerpts are never translated in either case — see
[the translation module](backend/app/qa/translate.py) for why.

**Prose that misreads a correct quotation is not measured.** Every reported metric is
deterministic, which is a strength and also a boundary. The checks establish that a cited
section exists, that retrieval put it in front of the model, and that a quoted excerpt is
the section's own words. They do not establish that the surrounding sentences characterise
that excerpt correctly. An answer that quotes section 54 accurately and then describes it
wrongly passes every check here. Measuring it needs either a calibrated judge or manual
scoring, and the reasoning for taking neither is in [eval/README.md](eval/README.md).

**Case law is out of scope.** The corpus is statutory. Judicial interpretation frequently
determines how a provision operates in practice, and none of it is here.

**Consolidation lag.** The corpus is only as current as bdlaws. A recent amendment not yet
reflected there will not be reflected here.

**Not a substitute for advice.** The system is designed to be verifiable, not authoritative.
Every citation links back to the official source precisely so that a user can check it.

## Future improvements

Ingest the Bangla texts for bilingual excerpts. Extend the corpus under the ADR 0007
criterion. Investigate act-aware retrieval ranking, which becomes a real problem once general
and special provisions on the same subject compete for the same query.

Hybrid retrieval — BM25 fused with dense by reciprocal rank — was planned as stage 4 and
replaced by structured offence lookup, which addressed the question that motivated it more
directly. It is untried rather than rejected, and remains the obvious next retrieval
experiment.

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Diagrams, data model, technology choices |
| [DATA_SOURCE.md](DATA_SOURCE.md) | Corpus provenance and source structure findings |
| [EXPERIMENTS.md](EXPERIMENTS.md) | Experiment log |
| [eval/README.md](eval/README.md) | Evaluation methodology |
| [AI_USAGE.md](AI_USAGE.md) | AI tooling, delegation, review, rejected suggestions |
| [docs/adr/](docs/adr/) | Architecture decision records |

## Attribution

Statutory text is reproduced from [bdlaws.minlaw.gov.bd](https://bdlaws.minlaw.gov.bd),
published by the Legislative and Parliamentary Affairs Division, Ministry of Law, Justice and
Parliamentary Affairs, Government of Bangladesh.
