"""Harness CLI wiring.

Every flag here is tested for being *consulted*, not merely accepted.

This file exists because of a real bug: a patch added `--wait-for-budget` to the
argument parser but failed to apply the change that reads it, because the
surrounding code had moved. The flag appeared in `--help`, argparse accepted it
without complaint, lint passed — and an overnight run stopped on the first daily
limit instead of waiting through it. Nothing short of running it, or a test like
this, would have caught it.
"""

from __future__ import annotations

import inspect

import pytest

from app.evaluation import harness


def _captured(monkeypatch) -> dict:
    seen: dict = {}

    async def fake_run_stage(stage, **kwargs):
        seen["stage"] = stage
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(harness, "run_stage", fake_run_stage)
    return seen


@pytest.mark.parametrize(
    ("argv", "key", "expected"),
    [
        (["--wait-for-budget"], "wait_for_budget", True),
        ([], "wait_for_budget", False),
        (["--provider", "ollama"], "provider_name", "ollama"),
        (["--no-cache"], "use_cache", False),
        ([], "use_cache", True),
        (["--concurrency", "5"], "concurrency", 5),
        (["--limit", "7"], "limit", 7),
    ],
)
def test_each_flag_reaches_run_stage(monkeypatch, argv, key, expected):
    seen = _captured(monkeypatch)

    harness.main(argv)

    assert seen[key] == expected


def test_run_stage_accepts_every_argument_main_passes(monkeypatch):
    """A flag main passes that run_stage does not accept is a TypeError at the
    worst possible moment — after a long sweep has already spent its budget."""
    # Capture the real signature before the stub replaces it.
    accepted = set(inspect.signature(harness.run_stage).parameters)

    seen = _captured(monkeypatch)
    harness.main(["--wait-for-budget", "--provider", "ollama", "--no-cache"])

    assert set(seen) - {"stage"} <= accepted


def test_run_stage_reads_the_flag_rather_than_only_accepting_it():
    """The exact bug: the parameter existed in the signature while the body never
    consulted it."""
    source = inspect.getsource(harness.run_stage)

    assert "wait_for_budget" in source.split(") -> int:", 1)[1]
