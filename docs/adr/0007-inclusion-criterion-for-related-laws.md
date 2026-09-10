# 7. Inclusion criterion for related laws

**Status:** Accepted · **Date:** 2026-09-10

## Context

The objective names "related laws of Bangladesh" without enumerating them. An open-ended
reading invites a corpus that grows by intuition, where each addition seems reasonable and
the whole is unjustifiable. A minimal reading — the Code alone — produces a system that is
confidently wrong on common questions.

The Code of Criminal Procedure is *procedural*. It is structurally incomplete on its own,
and it says so in its own text:

- s.4(1) provides that words and expressions used in the Code and defined in the Penal Code
  carry the meanings assigned there.
- s.5 is headed *Trial of offences under the Penal Code* and *Trial of offences against
  other laws*.
- s.4(1)(b) and s.4(1)(f) define *bailable* and *cognizable* offence by reference to the
  second schedule, which classifies Penal Code offences.

Separately, several Bangladeshi statutes contain non-obstante clauses that displace CrPC
procedure for offences under them. Where such an act applies, the general CrPC position on
bail, cognizance or trial forum is not merely incomplete — it is wrong.

## Decision

An act is in corpus scope if either limb holds:

1. **Normative reference.** CrPC gives it operative effect — its definitions, classifications
   or procedures are incorporated by reference into the Code.
2. **Procedural displacement.** It overrides CrPC procedure for offences under it, typically
   via a non-obstante clause.

Applying the criterion:

| Act | Limb | Rationale |
|---|---|---|
| Code of Criminal Procedure, 1898 | — | Core |
| Penal Code, 1860 | 1 | Supplies definitions the Code incorporates; Schedule II classifies its offences |
| Evidence Act, 1872 | 1 | Governs evidence in proceedings the Code creates |
| Special Powers Act, 1974 | 2 | Displaces ordinary bail and detention procedure |
| Nari-o-Shishu Nirjatan Daman Ain, 2000 | 2 | Special tribunals, distinct procedure |
| Cyber Security Act, 2023 | 2 | Distinct cognizance and bail provisions |

Acts are added one at a time, each addition demonstrating the incremental-update path
required by the brief, and each accompanied by an evaluation run so that a related law which
degrades retrieval on core CrPC questions is detected rather than assumed harmless.

The criterion is a filter, not a quota. An act satisfying neither limb stays out however
relevant it may seem topically.

## Consequences

Corpus growth is justified per act, in writing, against a stated rule. A reviewer can
disagree with the rule; they cannot mistake the corpus for an arbitrary pile.

Limb 2 is the one that earns its keep. A user asking about bail for an offence under a
special act, answered from CrPC alone, receives a fluent and correctly cited answer that is
legally wrong. Because it retrieves and cites successfully, no metric short of a
special-law evaluation slice detects it. The evaluation dataset therefore carries such a
slice deliberately.

Multi-act retrieval introduces a ranking problem the single-act corpus does not have:
general and special provisions on the same subject compete, and the general provision is
often the better lexical match. Whether retrieval must become act-aware is an open question
to be settled by measurement once the second act is ingested, not by assumption now.
