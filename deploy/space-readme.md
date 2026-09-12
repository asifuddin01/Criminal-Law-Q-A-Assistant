---
title: Criminal Law Q&A — Bangladesh
emoji: ⚖️
colorFrom: indigo
colorTo: gray
sdk: gradio
app_file: space_app.py
python_version: "3.12"
pinned: false
preload_from_hub:
  - qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q
short_description: Source-grounded Q&A over the Code of Criminal Procedure, 1898
---

# Criminal Law Q&A — Bangladesh

Source-grounded question answering over the Code of Criminal Procedure, 1898, its
Schedule II, and the Penal Code, 1860. Every answer is generated only from retrieved
statutory text and carries section-level citations with verbatim excerpts, each checked
against the stored source before it is shown. Where the corpus does not support an
answer, the system says so instead of producing one.

**This provides legal information, not legal advice.** Statutory text may have been
amended after the corpus snapshot, and retrieval may be incomplete. Verify against the
official text published by the Ministry of Law, Justice and Parliamentary Affairs.

## What to try

- *When may a police officer arrest a person without a warrant?* — returns section 54,
  with the note that it was substituted by Act XI of 2026 with effect from 10 August 2025
- *Is theft a bailable offence?* — answered from the Schedule II row for Penal Code
  section 379, looked up by offence name rather than retrieved
- *পুলিশ কখন বিনা পরোয়ানায় গ্রেপ্তার করতে পারে?* — Bangla question, English corpus,
  answer translatable on demand with the statutory excerpts left in English
- Something the corpus does not cover — the system should decline and say what it would
  need

Speech, image (OCR) and document upload are wired to the same pipeline: every modality
is normalised to text at the API boundary, so one evaluation covers all of them.

## How this is put together

Docker Spaces are not on this account's tier, so it runs under the `gradio` SDK — which
does not mean it *is* a Gradio interface. Spaces runs `app.py` and proxies port 7860, and
what serves that port is the project's own FastAPI application: the exported Next.js
frontend at `/`, the API under `/api`. A small Gradio block sits at `/gradio` so the
runtime finds the app its SDK expects.

Everything a Dockerfile would have done at build time is committed instead, because this
SDK has no build step: the frontend export, the parsed Schedule II, the corpus and the
vector index.

## Limits of this deployment

It runs on a free-tier token allowance shared by everyone using the link. When that is
spent the app says so and recovers on its own; nothing else is broken. The Space also
sleeps when idle, so the first request after a quiet period is slow.

Source, evaluation and the experiment log: https://github.com/asifuddin01/Criminal-Law-Q-A-Assistant
