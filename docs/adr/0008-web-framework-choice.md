# 8. Web framework: FastAPI

**Status:** Accepted · **Date:** 2026-09-10

## Context

FastAPI was adopted in the initial scaffold without the alternatives being examined. The
question was raised directly — is there a better Python API framework for this system — and
an unexamined default is not a technology choice, so it is examined here.

The system's actual requirements of a web framework are modest and specific:

- Async I/O throughout, since every request is dominated by network calls to a model provider
- Streaming responses, so an answer and its citations render progressively
- Multipart upload for audio, images and PDFs
- Request/response validation against Pydantic models already used elsewhere
- Generated OpenAPI documentation, which doubles as the API deliverable
- Singleton lifecycle for expensive resources: embedding model, vector client, provider

## Decision

Retain FastAPI.

### The performance argument does not apply

The per-request latency budget for one grounded answer:

| Stage | Order of magnitude |
|---|---|
| LLM generation | 500 ms – 5 s |
| Query embedding | 10–100 ms |
| Hybrid retrieval | 1–20 ms |
| Citation validation | < 1 ms |
| Framework overhead | < 1 ms |

Framework serialization sits roughly three orders of magnitude below the dominant term. A
framework chosen for throughput would optimise the only component whose contribution cannot
be measured against the noise in the LLM call. In a project that settles choices by
measurement, that change could not be justified with a number.

### Alternatives considered

**Litestar.** The strongest contender. msgspec-based serialization and a dependency-injection
system that handles singletons more gracefully than FastAPI's per-request model — relevant
here, since the embedding model, vector client and provider are all long-lived. Rejected
because FastAPI's `lifespan` plus a small cached registry already covers the singleton case
adequately, and because the smaller ecosystem offers fewer worked examples for the parts of
this system most likely to be fiddly: multipart audio upload, SSE streaming, and
transcription endpoints.

**Django with Django Ninja.** The one alternative with a requirement-shaped advantage.
Django's admin would supply corpus administration — adding, replacing and inspecting legal
documents — which the brief asks for, essentially free. Rejected because the corpus
administration surface needed here is one upload endpoint and a status view, and adopting an
ORM and migration system for it means subsequently working around that ORM for vector
storage. Revisit if corpus administration grows into a substantial interface.

**Flask or Quart.** A regression on typing and, for Flask, on async.

**BlackSheep, Robyn, Sanic.** Fast, with thinner ecosystems, and no advantage that maps onto
a requirement above.

## Consequences

Existing working, tested code is retained, and the week's remaining time goes to retrieval
correctness, which is where this system's quality actually lives.

FastAPI is widely known, so a reviewer reads familiar code and spends attention on the parts
that matter rather than on framework idioms.

The known weaknesses are accepted with mitigations rather than ignored:

*Background work.* `BackgroundTasks` is inadequate for ingestion — parsing a 3.84 MB PDF or
re-embedding an act must not occupy a request. Ingestion is therefore modelled as a job with
an identifier and a pollable status endpoint, not as a long request.

*Per-request dependency injection.* Expensive singletons are constructed once at application
startup and reached through a cached registry, not resolved per request.

*Router sprawl.* Accepted; the API surface here is small.

## What would actually improve the API

Recorded because these, not the framework, are where API quality is available:

1. Server-sent events for answer streaming, so citations resolve progressively
2. Ingestion as a job with pollable status
3. Request identifiers and structured logging, which is what makes the failure-analysis
   deliverable tractable — any bad answer can be traced to the exact retrieval set behind it
4. Response caching keyed on question hash, to protect free-tier quota across evaluation runs
