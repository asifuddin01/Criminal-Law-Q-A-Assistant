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

Early. Design and scaffold are in place; the retrieval pipeline is not yet built. This table
is the honest state of the repository, not a roadmap.

| Component | State |
|---|---|
| Architecture decisions | Recorded — [docs/adr/](docs/adr/) |
| Source survey | Complete — [DATA_SOURCE.md](DATA_SOURCE.md) |
| Evaluation methodology | Defined — [eval/README.md](eval/README.md) |
| Backend service, provider abstraction | Working, tested, connected to Groq |
| Ingestion pipeline | Parser working, tested — 522 sections, 599 amendments |
| Retrieval and generation | Not built |
| Evaluation dataset | Built — 95 questions, all labels validated |
| Frontend | Not built |

## Architecture

Full diagrams and the data model: **[docs/architecture.md](docs/architecture.md)**.

Two pipelines meet at the index. Ingestion parses statutory sources into sections, amendment
records and schedule rows. Query normalizes every input modality to text, retrieves under a
role filter, generates, and then passes the answer through a deterministic citation gate that
can refuse it.

Three decisions shape most of the design:

**The section is the unit of citation.** Chunks never cross section boundaries, because a
citation that cannot name a section is not verifiable.
([ADR 0002](docs/adr/0002-reassemble-pages-into-legal-sections.md),
[0005](docs/adr/0005-ingest-from-single-document-print-view.md))

**Documents carry a role, and only operative law is retrievable as law.** An amending act's
text is a diff, not a provision. Indexing it flat alongside the Code lets a question about
what a section provides retrieve a 1976 ordinance's instruction to delete a word — genuine
text, resolving citation, wrong answer.
([ADR 0006](docs/adr/0006-document-roles-separate-operative-law-from-amending-instruments.md))

**Modality is erased at the API boundary.** Speech, image and text converge on
`(question_text, attached_documents, language)` before retrieval, so one evaluation harness
covers every input path.
([ADR 0004](docs/adr/0004-normalize-input-modalities-at-the-boundary.md))

### Technology

| Layer | Choice |
|---|---|
| Backend | FastAPI, Python 3.12 ([why](docs/adr/0008-web-framework-choice.md)) |
| Frontend | Next.js |
| Generation | Groq `openai/gpt-oss-120b`, Ollama `qwen2.5:3b-instruct` fallback |
| Speech | Groq `whisper-large-v3` |
| Embeddings | `multilingual-e5-small` |
| Retrieval | BM25 + dense, reciprocal rank fusion |

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

Run the service:

```bash
cd backend && uv run uvicorn app.main:app --reload
```

- Interactive API docs: `http://localhost:8000/docs`
- Liveness: `GET /api/health` — deliberately does not touch the model provider
- Capabilities: `GET /api/meta?probe=true` — reports the active provider and what it supports

Tests:

```bash
cd backend && uv run pytest
```

## Data ingestion and update

Sources, structure and provenance: **[DATA_SOURCE.md](DATA_SOURCE.md)**.

The corpus comes from `bdlaws.minlaw.gov.bd`, published by the Legislative and Parliamentary
Affairs Division. Three source shapes:

| Shape | Endpoint | Handling |
|---|---|---|
| Whole act | `act-print-<id>.html` | One request per act. Segmented by section marker; footnotes parsed into amendment records |
| Schedule | `upload/act/…Schedule-II.pdf` | Table extraction into structured rows |
| Amending acts | Individual acts | Ingested with role `amending`, excluded from retrieval as law |

Membership follows a stated criterion rather than intuition: an act is in scope if CrPC
incorporates it by normative reference, or if it displaces CrPC procedure via a non-obstante
clause ([ADR 0007](docs/adr/0007-inclusion-criterion-for-related-laws.md)).

**Updating.** Sections carry a content hash, so re-ingesting an act re-embeds only what
changed. Adding a related act is the same operation as updating one, which is what makes the
incremental-update demonstration a normal code path rather than a special case. Each addition
is followed by an evaluation run, so an act that degrades retrieval on core CrPC questions is
detected rather than presumed harmless.

## Evaluation

Metrics, dataset schema and construction protocol: **[eval/README.md](eval/README.md)**.

The same dataset runs after every stage, so each change is attributable to a movement in a
number and a change that moves nothing is recorded as such. Five metrics; three are
deterministic. Faithfulness uses an LLM judge checked against a manually scored subset each
stage.

The dataset is stratified — direct lookup, multi-section, amended provisions, unanswerable,
ambiguous, Bangla. The unanswerable and ambiguous slices are not padding: a system tuned only
on answerable questions reliably learns to always answer.

Gold section labels are verified against fetched act text, never recalled. A wrong gold label
penalises correct retrieval and rewards incorrect retrieval, invisibly.

## Experiments and results

Running log with hypotheses, configurations, results and decisions:
**[EXPERIMENTS.md](EXPERIMENTS.md)**.

No measured results yet. The first entry records the source survey and the ingestion reversal
it caused.

## Limitations

Stated now rather than discovered later.

**No point-in-time reconstruction.** The system reports when a provision changed and under
which act, but does not reconstruct the text as it stood on a past date. bdlaws publishes
only the current consolidation, and the footnotes do not always preserve replaced wording in
full. Approximating this would be worse than declining it.

**English corpus.** Bangla questions are supported against English statutory text. The Bangla
texts on bdlaws are not yet ingested, so answers and quoted excerpts are in English.

**Image input has no provider yet.** The Groq catalogue available to this project
offers no vision-capable model, so image questions cannot currently be served. The
capability system degrades correctly rather than failing at call time, but the feature
is unimplemented pending a decision on the path — local OCR or a second provider.

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
