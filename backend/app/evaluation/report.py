"""Charts and tables from evaluation runs.

    python -m app.evaluation.report

Nothing in this project is trained, so there are no loss curves. The equivalent
artefact is the movement of a fixed evaluation set across stages: the same 95
questions, re-run after every change, so each stage's contribution is attributable.
"""

from __future__ import annotations

import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUNS_DIR = REPO_ROOT / "eval" / "runs"
CHARTS_DIR = RUNS_DIR / "charts"

# Higher is better for all of these except the hallucination rate, which is inverted
# when plotted so that "up" means "better" everywhere on the progression chart.
# Below this, losing a few questions is noise; above it, the surviving sample may
# be skewed toward whichever slices happened to complete.
MATERIAL_LOSS = 0.05


def _materially_incomplete(run: dict) -> bool:
    return run["questions"] and run["errors"] / run["questions"] > MATERIAL_LOSS


HEADLINE = [
    ("retrieval_recall", "Retrieval recall"),
    ("citation_precision", "Citation precision"),
    ("answer_hit_rate", "Answer hit rate"),
    ("excerpt_validity", "Excerpt validity"),
    ("refusal_accuracy", "Refusal accuracy"),
]

INK = "#1f2933"
MUTED = "#7b8794"
SERIES = ["#2a6f97", "#e07a5f", "#5f8d4e", "#8e7cc3", "#c9922e"]


def load_runs() -> list[dict]:
    """Complete runs only, and never from scratch.

    Charts are report artefacts. A partial run plotted beside complete ones is a
    misleading picture, so partial runs are excluded here rather than annotated.
    """
    runs = []
    for path in sorted(RUNS_DIR.glob("stage-*/summary.json")):
        if "scratch" in path.parts:
            continue
        run = json.loads(path.read_text(encoding="utf-8"))
        if run.get("partial"):
            continue
        runs.append(run)
    return sorted(runs, key=lambda r: (r.get("model", ""), r["stage"]))


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.label.set_color(MUTED)
    ax.grid(axis="y", color="#e4e7eb", linewidth=0.8)
    ax.set_axisbelow(True)


def group_by_model(runs: list[dict]) -> dict[str, list[dict]]:
    """Runs grouped by the model that produced them.

    A progression line must never span two models. Stage-to-stage movement is only
    interpretable when the model is held constant — otherwise a rise could be
    retrieval improving or simply a stronger model, and the chart cannot say which.
    """
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        grouped.setdefault(run.get("model", "unknown"), []).append(run)
    return {
        model: sorted(items, key=lambda r: r["stage"])
        for model, items in grouped.items()
    }


def chart_progression(runs: list[dict], *, model: str = "") -> pathlib.Path:
    """Headline metrics across stages — the closest thing this project has to a
    training curve, and the chart the report should lead with."""
    labels = [
        f"Stage {r['stage']}\n{r['system']}\n{r['measured']}/{r['questions']} measured"
        + ("  ⚠ incomplete" if _materially_incomplete(r) else "")
        for r in runs
    ]
    x = range(len(runs))

    fig, ax = plt.subplots(figsize=(9, 5))
    for index, (key, label) in enumerate(HEADLINE):
        values = [
            None if r.get(key) is None else r[key] * 100 for r in runs
        ]
        points = [(i, v) for i, v in zip(x, values, strict=True) if v is not None]
        if not points:
            continue
        ax.plot(
            [p[0] for p in points],
            [p[1] for p in points],
            marker="o",
            linewidth=2,
            markersize=6,
            color=SERIES[index % len(SERIES)],
            label=label,
        )

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9, color=INK)
    ax.set_ylim(-4, 104)
    ax.set_ylabel("percent")
    subtitle = f" — {model}" if model else ""
    ax.set_title(
        f"Evaluation metrics by stage{subtitle}\nsame 95 questions throughout",
        color=INK,
        fontsize=12,
        pad=14,
        loc="left",
    )
    _style(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, ncols=2)
    if any(_materially_incomplete(r) for r in runs):
        fig.text(
            0.01,
            0.01,
            f"⚠ A stage marked incomplete lost over {MATERIAL_LOSS:.0%} of questions "
            "to provider errors. Its rates cover measured questions only and may be "
            "skewed toward whichever slices completed.",
            fontsize=8,
            color=MUTED,
        )
    fig.tight_layout(rect=(0, 0.04, 1, 1))

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CHARTS_DIR / f"metric-progression{'-' + _slug(model) if model else ''}.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def _slug(text: str) -> str:
    return text.replace("/", "-").replace(":", "-").replace(".", "-")


def chart_hallucination(runs: list[dict], *, model: str = "") -> pathlib.Path:
    """What the system invents, against what it merely misfiles.

    Three bars, because "invalid quotation" was two different failures added
    together. A quotation that is real statutory text under the wrong section is a
    chunking failure; one that appears in no section is the model writing law. They
    move in opposite directions across the stages and no single bar shows that.
    """
    labels = [f"Stage {r['stage']}" for r in runs]
    hallucinated = [(r.get("hallucinated_citation_rate") or 0) * 100 for r in runs]

    def rate(run: dict, key: str) -> float:
        value = run.get(key)
        if value is not None:
            return value * 100
        # A run scored before the split: everything invalid counted as fabricated.
        if key == "fabrication_rate" and run.get("excerpt_validity") is not None:
            return 100 - run["excerpt_validity"] * 100
        return 0.0

    fabricated = [rate(r, "fabrication_rate") for r in runs]
    misattributed = [rate(r, "misattribution_rate") for r in runs]

    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    width = 0.26
    positions = range(len(runs))
    ax.bar(
        [p - width for p in positions],
        hallucinated,
        width,
        label="Citations to sections that do not exist",
        color=SERIES[1],
    )
    ax.bar(
        list(positions),
        fabricated,
        width,
        label="Quotations found in no section at all",
        color=SERIES[3],
    )
    ax.bar(
        [p + width for p in positions],
        misattributed,
        width,
        label="Real text, quoted under the wrong section",
        color=SERIES[4],
    )
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels, color=INK)
    ax.set_ylabel("percent (lower is better)")
    ax.set_title(
        f"Fabrication, by stage{' — ' + model if model else ''}",
        color=INK,
        fontsize=12,
        pad=14,
        loc="left",
    )
    _style(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CHARTS_DIR / f"fabrication{'-' + _slug(model) if model else ''}.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def chart_slices(runs: list[dict]) -> pathlib.Path | None:
    """Per-slice accuracy for the most recent complete stage."""
    if not runs:
        return None
    run = runs[-1]
    slices = run.get("by_slice") or {}
    names = sorted(slices)
    if not names:
        return None

    measured = [slices[n]["measured"] for n in names]
    accuracy = [
        (slices[n]["refusal_accuracy"] or 0) * 100 if slices[n]["measured"] else 0
        for n in names
    ]

    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(names, accuracy, color=SERIES[0], width=0.6)
    for bar, count in zip(bars, measured, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 2,
            f"n={count}",
            ha="center",
            fontsize=8,
            color=MUTED,
        )
    ax.set_ylim(0, 108)
    ax.set_ylabel("answer/refuse decided correctly (%)")
    ax.set_title(
        f"Stage {run['stage']} by slice — measured questions only",
        color=INK,
        fontsize=12,
        pad=14,
        loc="left",
    )
    _style(ax)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right", color=INK)
    fig.tight_layout()

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CHARTS_DIR / "slices.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def chart_retrieval() -> pathlib.Path | None:
    """Recall by cutoff for each chunking strategy.

    No model is involved, so any difference here is attributable to chunking alone.
    Recall is also the ceiling on everything downstream: generation cannot cite a
    section retrieval never returned.
    """
    source = RUNS_DIR / "retrieval" / "summary.json"
    if not source.exists():
        return None
    results = json.loads(source.read_text(encoding="utf-8"))

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11, 4.4))

    for index, result in enumerate(results):
        cutoffs = [int(k.lstrip("@")) for k in result["recall"]]
        values = [v * 100 for v in result["recall"].values()]
        ax.plot(
            cutoffs,
            values,
            marker="o",
            linewidth=2,
            color=SERIES[index % len(SERIES)],
            label=f"{result['strategy']} ({result['chunks']} chunks)",
        )
    ax.set_xlabel("k")
    ax.set_ylabel("recall (%)")
    ax.set_ylim(0, 104)
    ax.set_title("Retrieval recall by cutoff", color=INK, fontsize=12, pad=12, loc="left")
    _style(ax)
    ax.xaxis.label.set_color(MUTED)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)

    names = sorted({n for r in results for n in r["by_slice"]})
    width = 0.8 / max(1, len(results))
    for index, result in enumerate(results):
        positions = [
            i + index * width - 0.4 + width / 2 for i in range(len(names))
        ]
        values = [
            (result["by_slice"].get(n, {}).get("recall@10", 0)) * 100 for n in names
        ]
        bx.bar(
            positions,
            values,
            width,
            color=SERIES[index % len(SERIES)],
            label=result["strategy"],
        )
    bx.set_xticks(range(len(names)))
    bx.set_xticklabels(names, rotation=20, ha="right", color=INK)
    bx.set_ylabel("recall@10 (%)")
    bx.set_ylim(0, 108)
    bx.set_title("Recall@10 by slice", color=INK, fontsize=12, pad=12, loc="left")
    _style(bx)
    bx.legend(frameon=False, fontsize=9, labelcolor=INK)

    fig.tight_layout()
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CHARTS_DIR / "retrieval-recall.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


# Reported in the table but not charted. Excerpt validity counts a quotation that
# verified after a citation label was trimmed off it (ADR 0011); this counts only
# the ones that matched the statute as written. Publishing both means a reader who
# disagrees with the allowance can read the stricter number.
STRICT = ("excerpt_validity_unrepaired", "Excerpt validity (as written)")

# A failed quotation is either real text under the wrong section or text that is
# in no section at all. Reported separately because they have opposite fixes:
# misattribution is a chunking failure, fabrication is the model inventing law.
SPLIT = [
    ("misattribution_rate", "Misattributed"),
    ("fabrication_rate", "Fabricated"),
]


def markdown_table(runs: list[dict]) -> str:
    columns = [*HEADLINE, STRICT, *SPLIT]
    header = (
        "| Model | Stage | System | Measured | "
        + " | ".join(label for _, label in columns)
        + " |"
    )
    divider = "|---" * (4 + len(columns)) + "|"
    lines = [header, divider]
    for model, items in sorted(group_by_model(runs).items()):
        for run in items:
            cells = [
                "n/a" if run.get(key) is None else f"{run[key] * 100:.1f}%"
                for key, _ in columns
            ]
            covered = f"{run['measured']}/{run['questions']}"
            if run.get("missing_answers"):
                # The dataset grew after this run was recorded. Say so in the cell
                # rather than letting "93/93" read as complete coverage.
                covered += f" of {run['dataset_questions']}"
            lines.append(
                f"| {model} | {run['stage']} | {run['system']} | "
                f"{covered} | " + " | ".join(cells) + " |"
            )
    return "\n".join(lines)


def main() -> int:
    runs = load_runs()
    if not runs:
        print("no runs found; run: python -m app.evaluation.harness --stage 1")
        return 2

    written = []
    grouped = group_by_model(runs)
    for model, items in sorted(grouped.items()):
        # One chart per model. Never one line across two.
        label = model if len(grouped) > 1 else ""
        written.append(chart_progression(items, model=label))
        written.append(chart_hallucination(items, model=label))
        slices = chart_slices(items)
        if slices and len(grouped) == 1:
            written.append(slices)
    retrieval = chart_retrieval()
    if retrieval:
        written.append(retrieval)

    table = markdown_table(runs)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    (CHARTS_DIR / "results.md").write_text(table + "\n", encoding="utf-8")

    print(table)
    print()
    for path in written:
        print("wrote", path.relative_to(REPO_ROOT))
    print("wrote", (CHARTS_DIR / "results.md").relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
