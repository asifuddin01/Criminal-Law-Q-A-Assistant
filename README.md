# Criminal Law Q&A Assistant

A source-grounded question-answering assistant for Bangladesh criminal law, built on
the Code of Criminal Procedure, 1898 (Act No. V of 1898) together with its amendments
and related legislation.

Every answer is grounded in retrieved statutory text and carries section-level citations
with verbatim source excerpts. The system declines to answer when the corpus does not
support a confident response.

> **This system provides legal information, not legal advice.** It is not a substitute for
> a qualified advocate. Statutory text may have been amended after the corpus snapshot date.

## Status

Under active development. See [EXPERIMENTS.md](EXPERIMENTS.md) for the running log of
experiments and results, and [docs/adr/](docs/adr/) for architecture decisions.

## Documentation

| Document | Contents |
|---|---|
| [DATA_SOURCE.md](DATA_SOURCE.md) | Legal corpus provenance and document structure |
| [EXPERIMENTS.md](EXPERIMENTS.md) | Experiment log: hypotheses, configs, results, decisions |
| [AI_USAGE.md](AI_USAGE.md) | AI tooling used, tasks delegated, review process |
| [docs/adr/](docs/adr/) | Architecture decision records |
