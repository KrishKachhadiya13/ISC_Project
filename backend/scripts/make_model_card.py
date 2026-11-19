"""Fill the results sections of docs/MODEL_CARD.md from real result files.

Run from ``backend/`` after ``scripts.evaluate``::

    python -m scripts.make_model_card

Only the text between ``<!-- RESULTS:START -->`` and ``<!-- RESULTS:END -->``
is rewritten; the hand-written sections (intended use, architecture, limits)
are left alone. Every number comes from ``results/metrics.json`` and
``models/cnn_v1.json``. Nothing is typed in by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

START = "<!-- RESULTS:START -->"
END = "<!-- RESULTS:END -->"
METHOD_NAMES = {
    "lsb_replace": "LSB replacement",
    "lsb_match": "LSB matching",
    "lsb2_replace": "2-LSB replacement (unseen in training)",
    "suniward_sim": "S-UNIWARD simulation (unseen in training)",
    "hill_sim": "HILL simulation (unseen in training)",
}
MODE_NAMES = {"keyed": "keyed", "sequential": "sequential", "simulated": "simulated"}
# The only techniques the detectors saw during training.
TRAINED_METHODS = ("lsb_replace", "lsb_match")


def build_parser() -> argparse.ArgumentParser:
    """Command-line options."""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=root / "results" / "metrics.json")
    parser.add_argument("--cnn-meta", type=Path, default=root / "models" / "cnn_v1.json")
    parser.add_argument("--card", type=Path, default=root.parent / "docs" / "MODEL_CARD.md")
    return parser


def _fmt(value: float | None, digits: int = 3) -> str:
    """Format a metric, with an en dash for unavailable values."""
    return "–" if value is None else f"{value:.{digits}f}"


def _cell(metrics: dict[str, Any], key: str, ci_key: str | None = None) -> str:
    """Value with its bootstrap interval when one was computed."""
    text = _fmt(metrics.get(key))
    interval = metrics.get(ci_key) if ci_key else None
    if interval:
        text += f" [{_fmt(interval[0], 2)}, {_fmt(interval[1], 2)}]"
    return text


def status_section(metrics: dict[str, Any], cnn_meta: dict[str, Any] | None) -> list[str]:
    """Describe which detectors are trained, from the data."""
    lines = ["### Status", ""]
    trained_cnn = "cnn_v1" in metrics["detectors"]
    if trained_cnn and cnn_meta:
        hyper = cnn_meta.get("hyperparameters", {})
        lines.append(
            f"**Trained.** `cnn_v1` completed {hyper.get('epochs_completed')} epochs "
            f"(best epoch {hyper.get('best_epoch')}) in {cnn_meta.get('training_time_seconds', 0) / 3600:.2f} h "
            f"on `{hyper.get('device')}` with seed {cnn_meta.get('seed')}; training methods: "
            f"{', '.join(hyper.get('training_methods', []))}. "
            f"Calibration temperature {cnn_meta.get('temperature'):.3f}. "
            f"Dataset: {cnn_meta.get('dataset_origin')} (splits {cnn_meta.get('split_counts')})."
        )
    else:
        lines.append(
            "**CNN not trained.** Only the classical detectors have results below; the CNN pipeline exists "
            "but no checkpoint has been evaluated."
        )
    lines += ["", f"Results generated: {metrics.get('generated_at', 'unknown')}.", ""]
    return lines


def results_tables(metrics: dict[str, Any]) -> list[str]:
    """One table per (method, mode), listing every detector at every payload."""
    names = metrics["detectors"]
    lines = ["### Test results", ""]
    lines.append(
        "All values are on held-out, cover-disjoint test images. Brackets are bootstrap 95% intervals "
        "where computed. P_E and TPR@1%FPR are shown as – when unavailable."
    )
    lines.append("")
    # Techniques seen in training first, then the unseen ones.
    pairs = sorted(
        {(c["method"], c["mode"]) for c in metrics["conditions"]},
        key=lambda pair: (pair[0] not in TRAINED_METHODS, pair),
    )
    for method, mode in pairs:
        subset = sorted(
            (c for c in metrics["conditions"] if c["method"] == method and c["mode"] == mode),
            key=lambda c: c["payload_bpp"],
        )
        lines += [
            f"#### {METHOD_NAMES.get(method, method)}, {MODE_NAMES.get(mode, mode)} embedding",
            "",
            "| bpp | Detector | ROC-AUC | P_E | TPR @ 1% FPR | Accuracy |",
            "|---|---|---|---|---|---|",
        ]
        for condition in subset:
            for key, info in names.items():
                entry = condition["detectors"].get(key)
                if entry is None:
                    continue
                lines.append(
                    f"| {condition['payload_bpp']:g} | {info['label']} | "
                    f"{_cell(entry, 'roc_auc', 'roc_auc_ci95')} | {_cell(entry, 'p_e', 'p_e_ci95')} | "
                    f"{_fmt(entry.get('tpr_at_1pct_fpr'))} | {_fmt(entry.get('accuracy'))} |"
                )
        lines.append("")
    return lines


def unseen_section(metrics: dict[str, Any]) -> list[str]:
    """Explain the techniques the detectors never saw in training, when results include any."""
    unseen = sorted({c["method"] for c in metrics["conditions"]} - set(TRAINED_METHODS))
    if not unseen:
        return []
    names = ", ".join(METHOD_NAMES.get(method, method) for method in unseen)
    return [
        "### Unseen techniques",
        "",
        f"The classical model and the CNN were trained only on {', '.join(TRAINED_METHODS)}. The tables "
        f"above also score them on: {names}. Nothing was retrained for these, so the numbers show how "
        "far each detector generalises to a technique it has not seen. Thresholds and ensemble weights "
        "were fixed on validation data of the trained techniques only. Simulated schemes change pixels "
        "the way the real scheme would but carry no recoverable message (see "
        "`app/core/stego/simulate.py`); they use a fixed subset of the test covers, so their sample "
        "counts are smaller (see the sample counts in the tables).",
        "",
    ]


def weakest_conditions(
    metrics: dict[str, Any],
    detector: str,
    count: int = 3,
    methods: tuple[str, ...] | None = None,
) -> list[str]:
    """The hardest conditions for one detector, computed from the data.

    ``methods`` restricts the search (for example to the trained techniques), so the
    near-chance scores on unseen adaptive schemes do not hide the real weak spots.
    """
    rows = [
        (c["detectors"][detector]["roc_auc"], c)
        for c in metrics["conditions"]
        if detector in c["detectors"] and (methods is None or c["method"] in methods)
    ]
    rows.sort(key=lambda item: item[0])
    return [
        f"- {METHOD_NAMES.get(c['method'], c['method'])}, {c['mode']}, {c['payload_bpp']:g} bpp: ROC-AUC {auc:.3f}"
        for auc, c in rows[:count]
    ]


def failure_section(metrics: dict[str, Any]) -> list[str]:
    """Where each trained detector is weakest, listed from the numbers."""
    lines = [
        "### Where the detectors struggle on the trained techniques (computed from the results)",
        "",
    ]
    for key, info in metrics["detectors"].items():
        if not info.get("trained"):
            continue
        weak = weakest_conditions(metrics, key, methods=TRAINED_METHODS)
        if weak:
            lines += [f"**{info['label']}** — lowest ROC-AUC:", *weak, ""]
    return lines


def mismatch_section(metrics: dict[str, Any]) -> list[str]:
    """The Section 8.2 mismatch experiment, if it was run."""
    mismatch = metrics.get("mismatch")
    if not mismatch:
        return ["### Mismatch experiment", "", "Not run (no `cnn_mismatch_replace` model).", ""]
    lines = [
        "### Mismatch experiment",
        "",
        mismatch["description"],
        "",
        "| Tested on | Mode | bpp | ROC-AUC | P_E |",
        "|---|---|---|---|---|",
    ]
    for condition in mismatch["conditions"]:
        for entry in condition["detectors"].values():
            lines.append(
                f"| {METHOD_NAMES.get(condition['method'], condition['method'])} | {condition['mode']} | "
                f"{condition['payload_bpp']:g} | {_cell(entry, 'roc_auc', 'roc_auc_ci95')} | "
                f"{_cell(entry, 'p_e', 'p_e_ci95')} |"
            )
    lines.append("")
    return lines


def notes_section(metrics: dict[str, Any]) -> list[str]:
    """Evaluation notes recorded by the evaluation script."""
    lines = ["### Evaluation notes", ""]
    lines += [f"- {note}" for note in metrics.get("notes", [])]
    latency = (metrics.get("latency_ms") or {}).get("cnn_v1_cpu_per_image")
    if latency is not None:
        lines.append(
            f"- CNN CPU inference latency: {latency:.1f} ms per image (single 256×256 image)."
        )
    lines.append("")
    return lines


def render(metrics: dict[str, Any], cnn_meta: dict[str, Any] | None) -> str:
    """Everything that goes between the markers."""
    lines = status_section(metrics, cnn_meta)
    lines += results_tables(metrics)
    lines += unseen_section(metrics)
    lines += failure_section(metrics)
    lines += mismatch_section(metrics)
    lines += notes_section(metrics)
    return "\n".join(lines).rstrip() + "\n"


def replace_block(card: str, block: str) -> str:
    """Swap the text between the markers, failing loudly if they are missing."""
    if START not in card or END not in card:
        raise ValueError(f"MODEL_CARD.md must contain {START} and {END}.")
    head, rest = card.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n\n{block}\n{END}{tail}"


def main(argv: list[str] | None = None) -> int:
    """Rewrite the generated part of the model card."""
    args = build_parser().parse_args(argv)
    if not args.metrics.is_file():
        print(f"{args.metrics} not found; run scripts.evaluate first.", file=sys.stderr)
        return 1
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    cnn_meta = (
        json.loads(args.cnn_meta.read_text(encoding="utf-8")) if args.cnn_meta.is_file() else None
    )
    updated = replace_block(args.card.read_text(encoding="utf-8"), render(metrics, cnn_meta))
    args.card.write_text(updated, encoding="utf-8")
    print(f"Updated {args.card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
