# 4. Normalize every input modality at the API boundary

**Status:** Accepted · **Date:** 2026-09-10

## Context

Beyond text input, the brief lists image input, speech input and document upload as optional
features. All three are in scope for this build.

The tempting design gives each modality its own path through the system — a speech endpoint
that transcribes and then answers, an image endpoint that captions and then answers. That
design duplicates retrieval, prompting and citation logic across paths, and it quietly
invalidates evaluation: a harness that exercises the text path proves nothing about the
speech path, even though the only difference between them is how the question was captured.

## Decision

Every modality is reduced at the API boundary to the same internal request:

```
(question_text, attached_documents[], language)
```

Speech is transcribed to `question_text`. An image is converted to `question_text` — a
transcription of visible text, or a description where the image is not textual — and
retained as an attached document for provenance. An uploaded PDF becomes an attached
document and, where the user intends it, a candidate for admission to the corpus.

Downstream of that boundary, retrieval, generation, citation validation and refusal logic
have no knowledge of how the question arrived.

## Consequences

The evaluation harness stays valid across every modality, because all modalities converge on
the same core before any retrieval happens. Modality-specific evaluation then reduces to
measuring the accuracy of the conversion step alone — transcription word error rate, for
instance — which can be assessed independently and against far smaller datasets.

Adding a modality later means writing one adapter, not extending the pipeline.

Information is lost in the reduction: prosody in speech, layout in an image. For this
application, where the question is a request for legal information, that loss is acceptable.
Retaining the original input as an attached document preserves it for the cases where it is
not.

Transcription and vision errors become question errors, and will surface as retrieval
failures with no obvious cause. The API therefore returns the normalized `question_text`
alongside the answer, so the user can see what the system believed they asked.
