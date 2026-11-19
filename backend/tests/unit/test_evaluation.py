"""Tests for score-level metrics, ensemble fitting, and the evaluate script."""

import json
from pathlib import Path

import numpy as np
import pytest

from app.steganalysis.classical.features import extract_features, statistical_fallback
from app.steganalysis.evaluation import (
    fit_ensemble_weights,
    metrics_from_scores,
    statistical_score_from_features,
    tpr_at_fpr,
    weighted_scores,
)
from scripts.evaluate import main as evaluate_main

LABELS = np.array([0, 0, 0, 0, 1, 1, 1, 1], dtype=np.int64)


def test_perfect_detector_metrics() -> None:
    """Perfect separation gives AUC 1, P_E 0 and full TPR at 1% FPR."""
    scores = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    metrics = metrics_from_scores(LABELS, scores, 0.5, bootstrap_resamples=50)
    assert metrics["roc_auc"] == 1.0
    assert metrics["p_e"] == 0.0
    assert metrics["tpr_at_1pct_fpr"] == 1.0
    assert metrics["confusion_matrix"] == [[4, 0], [0, 4]]
    assert metrics["roc_auc_ci95"] == [1.0, 1.0]


def test_random_detector_is_near_chance() -> None:
    """Scores unrelated to labels give AUC near 0.5 and P_E near 0.5."""
    rng = np.random.default_rng(0)
    labels = np.repeat([0, 1], 2000).astype(np.int64)
    metrics = metrics_from_scores(labels, rng.random(4000), 0.5)
    assert abs(float(metrics["roc_auc"]) - 0.5) < 0.05  # type: ignore[arg-type]
    assert float(metrics["p_e"]) > 0.45  # type: ignore[arg-type]


def test_tpr_at_fpr_respects_the_false_positive_budget() -> None:
    """With one high-scoring cover, TPR at 0% FPR counts only stego above it."""
    scores = np.array([0.1, 0.2, 0.3, 0.95, 0.5, 0.6, 0.97, 0.99])
    assert tpr_at_fpr(LABELS, scores, 0.0) == 0.5


def test_ensemble_prefers_the_informative_detector() -> None:
    """The grid search puts weight on the detector that separates the classes."""
    good = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    noise = np.array([0.9, 0.1, 0.8, 0.2, 0.3, 0.7, 0.4, 0.6])
    config = fit_ensemble_weights(LABELS, {"a": good, "b": noise}, "a", "b")
    weights = config["weights"]
    assert isinstance(weights, dict) and weights["a"] > weights["b"]
    thresholds = config["thresholds"]
    assert isinstance(thresholds, dict) and set(thresholds) == {"balanced", "low_false_alarm"}


def test_weighted_scores_rejects_zero_weights() -> None:
    """All-zero weights are meaningless."""
    with pytest.raises(ValueError):
        weighted_scores({"a": np.ones(2)}, {"a": 0.0})


def test_statistical_score_matches_the_fallback_detector() -> None:
    """The feature-vector shortcut reproduces statistical_fallback exactly."""
    image = np.random.default_rng(5).integers(0, 256, (64, 64), dtype=np.uint8)
    expected = float(statistical_fallback(image)["probability"])  # type: ignore[arg-type]
    assert statistical_score_from_features(extract_features(image)) == pytest.approx(
        expected, abs=1e-6
    )


def test_evaluate_falls_back_to_stored_classical_results(tmp_path: Path) -> None:
    """Without a CNN, metrics.json is built from classical_metrics.json only."""
    results = tmp_path / "results"
    results.mkdir()
    cell = {
        "accuracy": 0.9,
        "precision": 0.9,
        "recall": 0.9,
        "f1": 0.9,
        "roc_auc": 0.95,
        "confusion_matrix": [[9, 1], [1, 9]],
        "sample_count": 20,
    }
    classical = {
        "dataset_origin": "test",
        "seed": 1,
        "evaluations": {
            "lsb_replace|keyed|0.4": {
                "method": "lsb_replace",
                "mode": "keyed",
                "payload_bits_per_pixel": 0.4,
                "test": {"histogram_gradient_boosting": cell, "statistical_fallback": cell},
            }
        },
    }
    (results / "classical_metrics.json").write_text(json.dumps(classical), encoding="utf-8")
    code = evaluate_main(
        [
            "--fixed",
            str(tmp_path / "none"),
            "--models",
            str(tmp_path / "models"),
            "--results",
            str(results),
        ]
    )
    assert code == 0
    metrics = json.loads((results / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["conditions"][0]["detectors"]["classical"]["roc_auc"] == 0.95
    assert metrics["conditions"][0]["detectors"]["classical"]["p_e"] is None
    assert any("CNN not trained" in note for note in metrics["notes"])
    assert (results / "plots" / "roc_auc_vs_payload.png").is_file()
    # No P_E values exist without per-image scores, so no empty P_E plot is drawn.
    assert not (results / "plots" / "p_e_vs_payload.png").exists()


def test_evaluate_reports_failure_when_nothing_exists(tmp_path: Path) -> None:
    """No models and no stored results is an error, not empty output."""
    assert (
        evaluate_main(
            ["--fixed", str(tmp_path), "--models", str(tmp_path), "--results", str(tmp_path / "r")]
        )
        == 1
    )
