# 11. What counts as a verbatim quotation

**Status:** Accepted · **Date:** 2026-09-12
**Amends:** the excerpt-validity metric defined in [EXPERIMENTS.md](../../EXPERIMENTS.md)
and the validation gate described in
[architecture.md](../architecture.md).

## Context

The system's central claim is that a quoted excerpt appears verbatim in the section it
is attributed to, checked deterministically rather than by asking a model whether it
was honest. The check was a normalised substring test: collapse whitespace, lowercase,
and ask whether the quotation occurs in the section text.

Stage 4 of the four-stage sweep reported excerpt validity of 65.6%, against 80.4% once
the defects below were fixed. Reading the failures individually rather than trusting
the rate showed that most of them were faithful quotations that the test could not
recognise, for three distinct reasons.

**The source carries editorial apparatus.** bdlaws marks words inserted by amendment
with square brackets, and words repealed out of a provision with `[* * *]`. The
ingested text contains 664 brackets and 366 asterisk runs. Section 200 reads
`shall at once examine [upon oath the complainant ...]`. A model quoting that section
writes it without brackets, as any lawyer would: the brackets record how the section
reached its present form and are not part of what the legislature enacted. The
substring test rejected the quotation.

**Elision is ordinary legal practice.** A quotation that skips a passage with an
ellipsis is a normal way to quote a long provision, and was scored as a fabrication.

**A labelled extract invites the label into the quotation.** Each extract is
introduced by a synthesised heading — "Code of Criminal Procedure section 54. When
police may arrest without warrant". Models copy that heading into the quotation along
with the text. In stage 3, 20 of 98 quotations did — one in five. The words after the
label were exact; the label appears in no statute, so the whole quotation failed.

A fourth defect sat in the scorer rather than the quotations. `score_question` resolved
every citation against the Code of Criminal Procedure, ignoring the document the
citation claimed. A Schedule II quotation about theft was compared against Code section
379, which concerns appeals. The sections overlap in numbering for most of their range,
so this silently mis-scored the offence questions stage 4 exists to answer — and it had
already been fixed in the validation gate, which had its own copy of the same logic.

## Decision

One implementation of "does this quotation appear in this section", in
`app/qa/quoting.py`, used by both the validation gate and the scorer. The duplication
is what let the two drift apart.

The comparison stays a substring test over both sides. What changes is what counts as
the section's own words:

- **Editorial apparatus is canonicalised away on both sides.** Brackets are dropped and
  `[* * *]` closes up. Applied symmetrically, so it can never admit text absent from
  the source — only text differing from it in apparatus a quotation would not carry.
- **An elided quotation is checked segment by segment, in order.** Every segment must
  appear, and each must independently clear the 20-character floor, so an ellipsis
  cannot be used to stitch common fragments into an invented sentence.
- **A leading citation label is trimmed, and the remainder must verify.** What the user
  is shown is the trimmed text — the statute alone, without the label the model copied
  in front of it.

A quotation consisting *only* of a marginal note does not verify. The note is an
editor's summary, not enacted text, and presenting one as a quotation of the law is
the failure this system exists to prevent, not an instance of it.

Every allowance is named in the result. `excerpt_validity` is reported alongside
`excerpt_validity_unrepaired`, which counts only quotations that matched as written.

The cause is also addressed rather than only its measurement: the extract label is now
marked as a label and the quotable text is fenced in triple quotes, and the prompt says
to quote only from between them.

## Consequences

The measured effect, isolated by re-scoring the *same* cached answers so that only the
measurement changed:

| stage | excerpt validity, before | after | of which matched as written |
| --- | --- | --- | --- |
| 1 · baseline, no retrieval | 0.0% | **0.0%** | 0.0% |
| 2 · naive chunks | 54.4% | **57.1%** | 56.0% |
| 3 · legal-aware chunks | 40.8% | **61.2%** | 40.8% |
| 4 · full corpus | 65.6% | **80.4%** | 72.2% |

The baseline is the control, and it is the reason to believe this is a correction and
not a loosening. Stage 1 quotes from memory with no text in front of it. Of its 15
quotations, the allowances rescue **zero** — 13 are rejected outright and 2 cite a
section that does not exist. Every one is invented, and every one remains scored as
invented.

What each rate is made of, on the same answers:

| stage | matched as written | label trimmed | elision | rejected |
| --- | --- | --- | --- | --- |
| 1 · baseline | 0 | 0 | 0 | 15 |
| 2 · naive chunks | 51 | 1 | 0 | 39 |
| 3 · legal-aware chunks | 40 | 20 | 0 | 38 |
| 4 · full corpus | 70 | 7 | 1 | 19 |

Citation existence rises to 100.0% at stages 3 and 4. The apparent hallucinations were
Penal Code and Schedule II citations being resolved against the Code of Criminal
Procedure — the scorer's bug, not the model's.

The risk this accepts is that canonicalisation admits a quotation differing from the
source in bracketing. That is deliberate: the alternative is to require users and
models to reproduce bdlaws' editorial marks, which no one reading the law does. The
floor that still holds is unchanged — the words themselves, contiguous and in order,
must appear in the section cited.

Reporting two rates rather than one is the honest form of this decision. Anyone who
disagrees with an allowance can read the stricter column, which is published beside the
looser one for every stage.

## Amendment — 2026-09-14: two artifacts, and what a failed elision is

The hosted model's first complete stage 4 reported **11.2% fabrication** — worse than its
own stage 2 (3.9%) and than the local model at stage 4 (6.2%), while every other metric
improved. Read one at a time, **3 of the 18 were fabrications.** The rest were three
defects in how quotations were checked and classified, all invisible on the local model,
whose habits the allowances above were written against.

- **A non-breaking hyphen.** `gpt-oss-120b` writes "police‑station" with U+2011. The
  corpus contains no U+2010 or U+2011 at all, so a quotation containing one could not
  match however faithful its words. Both are now folded to `-` on both sides. En and em
  dashes are not: they are different marks, and the corpus has en dashes of its own.
  Three quotations.
- **Punctuation at the edge of an elided piece.** "…for which he is tried." where the
  statute reads "tried; and". The punctuation at either edge of a piece is the quoter's.
  The 20-character floor is applied to the words that remain, so it cannot pad a piece
  past it. One quotation.
- **Every failed elision was counted as fabrication.** The fallback that asks which
  section a failed quotation really came from was handed the whole string, ellipsis
  included — and an ellipsis appears in no statute. So a rejected elision was always
  "invented text", however real its words. Rejections are now classified four ways:
  *misattributed* (real text, another section), *fabricated* (text found in no section),
  *over-elided* (the cited section's own words, in its order, with a piece too short to be
  evidence) and *recomposed* (real pieces joined in an order, or from places, the statute
  does not use). The last two remain rejections. They are not fabrications, and a
  recomposed quotation — real words, a proposition the law does not state — is a failure
  worth its own name.

Measured by re-scoring the same stored answers, so only the measurement changed:

| run | excerpt validity | fabricated | over-elided | recomposed |
| --- | --- | --- | --- | --- |
| hosted stage 2 | 95.4% → 96.2% | 3.9% → 2.3% | 0.8% | 0.0% |
| hosted stage 3 | 88.5% → 90.9% | 11.5% → 0.6% | 8.5% | 0.0% |
| hosted stage 4 | 88.8% → 91.3% | 11.2% → 1.9% | 6.2% | 0.6% |

Hosted stage 3 finished two days after this amendment was written and is included on the
same terms: its harness process had loaded the scorer before the correction, so it was scored
under the old rule and re-scored under the new one from its stored answers. One of its
fifteen rejected quotations is a fabrication. Fourteen are the section's own words elided
past the floor.

**Unchanged, which is the evidence this is a correction:** both baselines stay at 0.0%
valid and 100% fabricated — the hosted baseline carries twenty non-breaking hyphens and
not one of its quotations is rescued — and all three local runs, which contain no
non-ASCII hyphens and no rejected elisions, do not move by a tenth of a point.
