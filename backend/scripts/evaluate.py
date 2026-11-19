"""Phase 7: evaluate every detector on the fixed sets and write results/metrics.json.

Run from ``backend/``::

    python -m scripts.evaluate --fixed data/cnn-fixed --workers 6

What it does (Section 8):

1. Scores every image of the fixed validation and test sets with the
   statistical detector, the trained classical model and the CNN.
2. Fits the ensemble weight and operating thresholds on **validation only**
   and saves them to ``models/ensemble.json`` (read by the API).
3. Computes test metrics (accuracy, F1, ROC-AUC, P_E, TPR@1%FPR, confusion
   matrix, bootstrap 95% CIs) per method × mode × payload × detector.
4. Adds the mismatch experiment if ``cnn_mismatch_replace`` exists.
5. Writes ``results/metrics.json`` and plots under ``results/plots/``.

If the CNN or fixed sets are missing it falls back to the stored classical
results and says so in the notes; it never invents numbers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import matplotlib
import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.steganalysis.classical.features import extract_features
from app.steganalysis.deep.calibration import calibrated_probabilities
from app.steganalysis.deep.infer import load_cnn_checkpoint
from app.steganalysis.deep.model import StegNetLite
from app.steganalysis.evaluation import (
    fit_ensemble_weights,
    metrics_from_scores,
    statistical_score_from_features,
    weighted_scores,
)

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402  (backend must be set first)

METHODS = ("lsb_replace", "lsb_match")
MODES = ("keyed", "sequential")
DETECTOR_LABELS = {
    "statistical": ("Statistical (untrained)", False),
    "classical": ("Classical ML (HGB)", True),
    "cnn_v1": ("CNN (StegNet-Lite)", True),
    "ensemble": ("Ensemble (HGB + CNN)", True),
}
Scores = dict[str, NDArray[np.float64]]


def build_parser() -> argparse.ArgumentParser:
    """Command-line options."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--fixed", type=Path, default=Path("data/cnn-fixed"))
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--workers", type=int, default=4, help="Processes for feature extraction.")
    parser.add_argument("--bootstrap", type=int, default=1000, help="Bootstrap resamples for CIs.")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--seed", type=int, default=1337)
    return parser


# ---------------------------------------------------------------- loading


def _load_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file if it exists."""
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _condition_dirs(fixed: Path, split: str) -> dict[tuple[str, str, float], Path]:
    """Map (method, mode, bpp) to its fixed-set folder for one split."""
    found: dict[tuple[str, str, float], Path] = {}
    for directory in sorted((fixed / split).glob("*_*_*")):
        meta = _load_json(directory / "metadata.json")
        if meta is None:
            continue
        found[(meta["method"], meta["mode"], float(meta["payload_bpp"]))] = directory
    return found


def _read_gray(path: Path) -> NDArray[np.uint8]:
    """Decode a fixed-set PNG as 8-bit grayscale."""
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


def _features_for(path: str) -> NDArray[np.float32]:
    """Worker: hand-crafted features for one image file."""
    return extract_features(_read_gray(Path(path)))


# ---------------------------------------------------------------- scoring


class Scorer:
    """Scores image files with every detector, caching identical covers."""

    def __init__(
        self,
        classical: Any,
        cnn: StegNetLite | None,
        temperature: float,
        device: torch.device,
        workers: int,
    ) -> None:
        """Hold the models and a cache keyed by file SHA-256."""
        self.classical = classical
        self.cnn = cnn
        self.temperature = temperature
        self.device = device
        # Threads, not processes: feature extraction is ~6 ms per image, and every spawned
        # process re-imported torch (~500 MB each), which exhausted RAM on this laptop.
        self.pool = ThreadPoolExecutor(max_workers=max(1, workers))
        self.cache: dict[str, dict[str, float]] = {}

    def close(self) -> None:
        """Shut down worker processes."""
        self.pool.shutdown()

    def score(self, paths: list[Path], hashes: list[str]) -> Scores:
        """Return per-detector probability arrays in the order of ``paths``."""
        todo = [index for index, digest in enumerate(hashes) if digest not in self.cache]
        if todo:
            features = list(
                self.pool.map(_features_for, [str(paths[i]) for i in todo], chunksize=32)
            )
            matrix = np.stack(features)
            classical = self.classical.predict_proba(matrix)[:, 1]
            cnn = (
                self._cnn_probabilities([paths[i] for i in todo]) if self.cnn is not None else None
            )
            for position, index in enumerate(todo):
                entry = {
                    "statistical": statistical_score_from_features(matrix[position]),
                    "classical": float(classical[position]),
                }
                if cnn is not None:
                    entry["cnn_v1"] = float(cnn[position])
                self.cache[hashes[index]] = entry
        names = self.cache[hashes[0]].keys()
        return {
            name: np.asarray([self.cache[d][name] for d in hashes], dtype=np.float64)
            for name in names
        }

    def _cnn_probabilities(self, paths: list[Path], batch: int = 128) -> NDArray[np.float64]:
        """Calibrated CNN probabilities for 256×256 grayscale files."""
        assert self.cnn is not None
        logits: list[float] = []
        for start in range(0, len(paths), batch):
            stack = (
                np.stack([_read_gray(p) for p in paths[start : start + batch]]).astype(np.float32)
                / 255.0
            )
            tensor = torch.from_numpy(stack).unsqueeze(1).to(self.device)
            with (
                torch.inference_mode(),
                torch.autocast(self.device.type, enabled=self.device.type == "cuda"),
            ):
                logits.extend(self.cnn(tensor).float().reshape(-1).cpu().tolist())
        return calibrated_probabilities(np.asarray(logits), self.temperature)


def score_condition(scorer: Scorer, directory: Path) -> tuple[NDArray[np.int64], Scores]:
    """Score all cover/stego pairs of one fixed set; labels are 0 cover, 1 stego."""
    meta = _load_json(directory / "metadata.json")
    assert meta is not None
    pairs = meta["pairs"]
    paths = [directory / p["cover"] for p in pairs] + [directory / p["stego"] for p in pairs]
    hashes = [p["cover_sha256"] for p in pairs] + [p["stego_sha256"] for p in pairs]
    labels = np.concatenate([np.zeros(len(pairs), np.int64), np.ones(len(pairs), np.int64)])
    return labels, scorer.score(paths, hashes)


# ---------------------------------------------------------------- main flow


def main(argv: list[str] | None = None) -> int:
    """Run the evaluation and write metrics, ensemble config and plots."""
    args = build_parser().parse_args(argv)
    args.results.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    classical_meta = _load_json(args.models / "classical_hgb.json") or _load_json(
        args.models / "classical_rf.json"
    )
    cnn_meta = _load_json(args.models / "cnn_v1.json")
    classical_results = _load_json(args.results / "classical_metrics.json")
    val_dirs = _condition_dirs(args.fixed, "val")
    test_dirs = _condition_dirs(args.fixed, "test")

    if classical_meta and cnn_meta and val_dirs and test_dirs:
        metrics = _full_evaluation(args, classical_meta, cnn_meta, val_dirs, test_dirs, notes)
    elif classical_results:
        metrics = _classical_only(classical_results, notes)
    else:
        print("Nothing to evaluate: no trained models or stored results.", file=sys.stderr)
        return 1

    metrics["notes"] = notes + metrics.get("notes", [])
    (args.results / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    _plot_summary(metrics, args.results / "plots")
    print(f"Wrote {args.results / 'metrics.json'} and plots in {args.results / 'plots'}")
    return 0


def _full_evaluation(
    args: argparse.Namespace,
    classical_meta: dict[str, Any],
    cnn_meta: dict[str, Any],
    val_dirs: dict[tuple[str, str, float], Path],
    test_dirs: dict[tuple[str, str, float], Path],
    notes: list[str],
) -> dict[str, Any]:
    """Score fixed sets with all detectors, fit the ensemble, compute test metrics."""
    device = torch.device("cuda" if args.device != "cpu" and torch.cuda.is_available() else "cpu")
    classical_name = str(classical_meta["model"])
    classical_model = joblib.load(args.models / f"{classical_name}.joblib")
    threshold_key = (
        "random_forest" if classical_name == "classical_rf" else "histogram_gradient_boosting"
    )
    classical_threshold = float(
        classical_meta["experiment"]["decision_thresholds_selected_on_validation"][threshold_key]
    )
    cnn, temperature = load_cnn_checkpoint(args.models / "cnn_v1.pt", device=device)
    cnn_threshold = float(
        calibrated_probabilities(
            np.asarray([cnn_meta["validation_selection"]["threshold"]]), temperature
        )[0]
    )
    thresholds = {"statistical": 0.5, "classical": classical_threshold, "cnn_v1": cnn_threshold}

    scorer = Scorer(classical_model, cnn, temperature, device, args.workers)
    try:
        # 1) Validation: fit the ensemble on every validation condition pooled.
        val_labels: list[NDArray[np.int64]] = []
        val_scores: dict[str, list[NDArray[np.float64]]] = {"classical": [], "cnn_v1": []}
        for key, directory in sorted(val_dirs.items()):
            labels, scores = score_condition(scorer, directory)
            val_labels.append(labels)
            for name in val_scores:
                val_scores[name].append(scores[name])
            print(f"scored val {key}", flush=True)
        pooled = {name: np.concatenate(parts) for name, parts in val_scores.items()}
        ensemble = fit_ensemble_weights(np.concatenate(val_labels), pooled, "classical", "cnn_v1")
        weights = ensemble["weights"]
        assert isinstance(weights, dict)
        thresholds["ensemble"] = float(ensemble["thresholds"]["balanced"])  # type: ignore[index]
        api_config = {
            **ensemble,
            "weights": {"rf": weights["classical"], "cnn": weights["cnn_v1"]},
            "fitted_on": "fixed validation sets (all methods, modes and payloads pooled)",
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        (args.models / "ensemble.json").write_text(
            json.dumps(api_config, indent=2) + "\n", encoding="utf-8"
        )

        # 2) Test: metrics per condition and detector.
        conditions = []
        for index, (key, directory) in enumerate(sorted(test_dirs.items())):
            labels, scores = score_condition(scorer, directory)
            scores["ensemble"] = weighted_scores(scores, weights)
            conditions.append(
                {
                    "method": key[0],
                    "mode": key[1],
                    "payload_bpp": key[2],
                    "detectors": {
                        name: metrics_from_scores(
                            labels,
                            values,
                            thresholds[name],
                            bootstrap_resamples=args.bootstrap,
                            seed=args.seed + index,
                        )
                        for name, values in scores.items()
                    },
                }
            )
            print(f"scored test {key}", flush=True)
    finally:
        scorer.close()

    cnn_results = _load_json(args.results / "cnn_metrics.json") or {}
    notes.extend(
        [
            "All detectors are scored on the same fixed, seeded test images (cover-disjoint from training).",
            "Thresholds and ensemble weights were chosen on validation data only.",
            f"Ensemble = {weights['classical']}×classical + {weights['cnn_v1']}×CNN, weight chosen by validation ROC-AUC.",
            "The classical model was trained on a separate Kaggle run of the same BOSSbase split; its stego training "
            "examples used different random keys than these fixed sets.",
            "The statistical detector is untrained; its 0.5 threshold is a fixed rule, not tuned.",
        ]
    )
    return {
        "format_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset_origin": str(cnn_meta.get("dataset_origin", "unknown")),
        "seed": args.seed,
        "detectors": {
            name: {
                "label": DETECTOR_LABELS[name][0],
                "trained": DETECTOR_LABELS[name][1],
                "source": source,
            }
            for name, source in (
                ("statistical", "rule-based"),
                ("classical", classical_name),
                ("cnn_v1", "cnn_v1"),
                ("ensemble", "models/ensemble.json"),
            )
        },
        "conditions": conditions,
        "ensemble": api_config,
        "latency_ms": {
            "cnn_v1_cpu_per_image": cnn_results.get("cpu_inference_latency_ms_per_image")
        },
        "mismatch": _mismatch_section(args.results),
        "fixed_sets_sha256": _hash_fixed_metadata(args.fixed),
    }


def _mismatch_section(results: Path) -> dict[str, Any] | None:
    """Section 8.2: CNN trained on replacement only, tested on both methods."""
    data = _load_json(results / "cnn_mismatch_replace_metrics.json")
    if not data:
        return None
    conditions = [
        {
            "method": item["method"],
            "mode": item["mode"],
            "payload_bpp": item["payload_bits_per_pixel"],
            "detectors": {"cnn_mismatch_replace": _cnn_metric_subset(item)},
        }
        for item in data["test_evaluations"].values()
    ]
    return {
        "description": "A CNN trained only on LSB replacement, evaluated on both replacement and matching. "
        "The gap on LSB matching measures how well it generalises to an unseen embedding method.",
        "conditions": sorted(conditions, key=lambda c: (c["method"], c["mode"], c["payload_bpp"])),
    }


def _cnn_metric_subset(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a train_cnn.py test entry to the metrics.json shape."""
    ci = item.get("bootstrap_95_ci", {})
    return {
        "accuracy": item["accuracy"],
        "precision": item["precision"],
        "recall": item["recall"],
        "f1": item["f1"],
        "roc_auc": item["roc_auc"],
        "p_e": item["p_e"],
        "tpr_at_1pct_fpr": item["tpr_at_1_percent_fpr"],
        "confusion_matrix": item["confusion_matrix"],
        "sample_count": item["sample_count"],
        "roc_auc_ci95": ci.get("roc_auc"),
        "p_e_ci95": ci.get("p_e"),
    }


def _classical_only(classical: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    """Fallback: reshape the stored classical results when no CNN exists yet."""
    rename = {
        "statistical_fallback": "statistical",
        "histogram_gradient_boosting": "classical",
        "random_forest": "classical_rf",
    }
    labels = {**DETECTOR_LABELS, "classical_rf": ("Classical ML (Random Forest)", True)}
    conditions = []
    for item in classical["evaluations"].values():
        detectors = {
            rename[name]: {**values, "p_e": None, "tpr_at_1pct_fpr": None}
            for name, values in item["test"].items()
            if name in rename
        }
        conditions.append(
            {
                "method": item["method"],
                "mode": item["mode"],
                "payload_bpp": item["payload_bits_per_pixel"],
                "detectors": detectors,
            }
        )
    notes.append("CNN not trained yet: only the stored classical results are shown.")
    notes.append(
        "The stored classical run did not keep per-image scores, so P_E and TPR@1%FPR are unavailable."
    )
    names = sorted({name for c in conditions for name in c["detectors"]})
    return {
        "format_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset_origin": classical.get("dataset_origin", "unknown"),
        "seed": classical.get("seed", 1337),
        "detectors": {
            n: {
                "label": labels[n][0],
                "trained": labels[n][1],
                "source": "results/classical_metrics.json",
            }
            for n in names
        },
        "conditions": sorted(conditions, key=lambda c: (c["method"], c["mode"], c["payload_bpp"])),
        "mismatch": None,
    }


def _hash_fixed_metadata(fixed: Path) -> str:
    """One hash over every fixed-set manifest, to tie metrics to exact images."""
    digest = hashlib.sha256()
    for path in sorted(fixed.glob("*/*/metadata.json")):
        digest.update(path.read_bytes())
    return digest.hexdigest()


# ---------------------------------------------------------------- plots


def _plot_summary(metrics: dict[str, Any], plots: Path) -> None:
    """P_E and ROC-AUC vs payload, one panel per (method, mode) present in the results."""
    plots.mkdir(parents=True, exist_ok=True)
    pairs = sorted({(c["method"], c["mode"]) for c in metrics["conditions"]})
    columns = 2
    rows = -(-len(pairs) // columns)  # ceiling division
    for key, title, ylim in (
        ("p_e", "P_E (lower is better)", (0, 0.55)),
        ("roc_auc", "ROC-AUC (higher is better)", (0.4, 1.0)),
    ):
        has_values = any(
            entry.get(key) is not None
            for c in metrics["conditions"]
            for entry in c["detectors"].values()
        )
        output = plots / f"{key}_vs_payload.png"
        if not has_values:
            # No numbers for this metric (e.g. P_E without per-image scores): no plot.
            output.unlink(missing_ok=True)
            continue
        figure, grid = plt.subplots(
            rows, columns, figsize=(11, 4 * rows), sharey=True, squeeze=False
        )
        for panel, (method, mode) in enumerate(pairs):
            axis = grid[panel // columns][panel % columns]
            subset = sorted(
                (c for c in metrics["conditions"] if c["method"] == method and c["mode"] == mode),
                key=lambda c: c["payload_bpp"],
            )
            for name, info in metrics["detectors"].items():
                points = [
                    (c["payload_bpp"], c["detectors"][name][key])
                    for c in subset
                    if name in c["detectors"] and c["detectors"][name].get(key) is not None
                ]
                if points:
                    axis.plot(*zip(*points, strict=True), marker="o", label=info["label"])
            axis.set_title(f"{method}, {mode}")
            axis.set_xlabel("payload (bpp)")
            axis.set_ylim(*ylim)
            axis.grid(alpha=0.3)
        for row_axes in grid:
            row_axes[0].set_ylabel(title)
            for axis in row_axes:
                if not axis.has_data():
                    axis.set_visible(False)  # an unused cell when the panel count is odd
        grid[0][0].legend(fontsize=8)
        figure.tight_layout()
        figure.savefig(output, dpi=110)
        plt.close(figure)


if __name__ == "__main__":
    raise SystemExit(main())
