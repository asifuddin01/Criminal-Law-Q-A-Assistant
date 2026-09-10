# 3. Pluggable LLM providers, Groq primary with a local fallback

**Status:** Accepted · **Date:** 2026-09-10

## Context

The brief permits a self-hosted model, vLLM, or a free or paid API. The development machine
is an Apple M1 with 8 GB of unified memory, which rules out self-hosting a model large
enough to reason reliably over statutory language; the locally available model is
`qwen2.5:3b-instruct` under Ollama.

The build plan also requires an LLM-only baseline with no retrieval, and repeated evaluation
runs after every subsequent stage. Both are cheap against a hosted API and slow against
local inference on this hardware.

Separately, the optional image, speech and document-upload features each need a model:
transcription for speech and a vision-capable model for images.

## Decision

All model access goes through a provider interface with a single implementation per backend,
selected by configuration. No call site names a provider.

Groq is the default: its free tier serves a large instruction model for generation,
`whisper-large-v3` for transcription — which covers Bangla — and a vision-capable model for
image input. One credential covers all three modalities.

Ollama with `qwen2.5:3b-instruct` is the fallback, giving an offline demonstration path and
satisfying the self-hosted option in the brief. It is not expected to match the hosted model
on answer quality, and the evaluation harness will record both so the gap is measured rather
than claimed.

## Consequences

The baseline experiment and every subsequent evaluation run are cheap, which is what makes
re-running the dataset after each change practical rather than aspirational.

The system has no single point of failure at demonstration time: if the hosted API is
unreachable, the local provider still answers.

Provider abstraction has a cost — it hides capabilities that differ between backends, such
as native structured output or vision support. The interface therefore declares capabilities
explicitly, and the application degrades a feature rather than failing when a configured
provider lacks it.

Free-tier rate limits are a real constraint on evaluation throughput. The harness caches
responses keyed on prompt hash so that a re-run after an unrelated change does not re-spend
quota.
