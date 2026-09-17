"""Where results are written, and what happens when the budget runs out.

Both are correctness concerns rather than conveniences. A run that writes to the
wrong place destroys a measurement; a run that writes a partial sweep publishes one
that looks complete.
"""

from __future__ import annotations

from app.evaluation.harness import (
    _explain_exhausted,
    _is_daily_limit,
    results_dir,
)


def test_each_provider_gets_its_own_results_track():
    """A local sweep must not land on top of a hosted one. Answers from two models
    in one directory describe neither."""
    assert results_dir(2, "groq").name == "stage-2"
    assert results_dir(2, "ollama").name == "stage-2-ollama"
    assert results_dir(2, "groq") != results_dir(2, "ollama")


def test_partial_runs_are_quarantined_in_scratch():
    """Regression: a three-question smoke run overwrote a complete 95-question
    result set. Git had it; nothing in the pipeline should rely on that."""
    partial = results_dir(2, "groq", partial=True)

    assert "scratch" in partial.parts
    assert partial != results_dir(2, "groq")


def test_partial_runs_stay_separated_per_provider_too():
    assert results_dir(3, "ollama", partial=True).name == "stage-3-ollama"
    assert "scratch" in results_dir(3, "ollama", partial=True).parts


def test_an_experiment_never_lands_on_the_canonical_track():
    """A variant run — the same stage under a changed prompt — must not replace
    the result every document cites. The report reads stage-* at the top level;
    an experiment goes somewhere it never looks."""
    run = results_dir(4, "ollama", experiment="clarification/after")

    assert run != results_dir(4, "ollama")
    assert run.parts[-4:] == ("experiments", "clarification", "after", "stage-4-ollama")


def test_a_slice_run_is_named_for_its_slices_and_quarantined_without_an_experiment():
    sliced = results_dir(4, "groq", partial=True, slices=["unanswerable", "ambiguous"])

    assert "scratch" in sliced.parts
    assert sliced.name == "stage-4-ambiguous-unanswerable"


def test_an_experiment_name_cannot_escape_the_runs_directory():
    import pytest

    for name in ("../stage-4", "a/../../b", ""):
        with pytest.raises(ValueError):
            results_dir(4, "ollama", experiment=name)


def test_daily_limit_is_told_apart_from_per_minute_limit():
    """They call for opposite responses: a per-minute limit is waited out inside a
    run, a per-day one cannot be."""
    daily = (
        "Rate limit reached ... on tokens per day (TPD): Limit 200000, Used 199180"
    )
    per_minute = (
        "Rate limit reached ... on tokens per minute (TPM): Limit 8000, Used 7456"
    )

    assert _is_daily_limit(daily) is True
    assert _is_daily_limit(per_minute) is False


def test_exhaustion_message_offers_both_choices_without_making_one(capsys):
    _explain_exhausted(
        3,
        "on tokens per day (TPD): Limit 200000, Used 199180",
        done=62,
        total=95,
        provider_name="groq",
    )
    out = capsys.readouterr().out

    assert "no results written" in out.lower()
    assert "1. WAIT" in out
    assert "2. SWITCH" in out
    assert "--provider ollama" in out
    assert "--stage 3" in out
    # It must say the fallback is whole-stage, not a mid-run swap.
    assert "WHOLE stage on ONE model" in out
    # And report what survives, so waiting is understood as resuming.
    assert "62 of 95" in out
