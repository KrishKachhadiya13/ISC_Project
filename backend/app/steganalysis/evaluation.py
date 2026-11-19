"""Score-level evaluation helpers and validation-fitted ensemble weights.

Everything here works on plain arrays of labels (0 = cover, 1 = stego) and
detector probabilities, so it is easy to test and to explain:

* ``metrics_from_scores`` — accuracy/F1 at a fixed threshold, plus the
  threshold-free ROC-AUC, P_E and TPR at 1% FPR (Section 8.3);
* ``fit_ensemble_weights`` — a documented weighted average whose weight is
  chosen on the validation split only (Section 6.10).
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

from app.steganalysis.deep.train import bootstrap_confidence_intervals, minimum_detection_error
from app.steganalysis.ensemble import select_operating_thresholds

WEIGHT_GRID = np.round(np.linspace(0.0, 1.0, 11), 2)


def tpr_at_fpr(
    labels: NDArray[np.int64], scores: NDArray[np.float64], max_fpr: float = 0.01
) -> float:
    """Highest true-positive rate reachable while false positives stay <= ``max_fpr``."""
    false_positive_rate, true_positive_rate, _ = roc_curve(labels, scores)
    allowed = true_positive_rate[false_positive_rate <= max_fpr]
    return float(allowed.max()) if allowed.size else 0.0


def metrics_from_scores(
    labels: NDArray[np.int64],
    scores: NDArray[np.float64],
    threshold: float,
    *,
    bootstrap_resamples: int = 0,
    seed: int = 1337,
) -> dict[str, object]:
    """Compute the Section 8.3 metrics for one detector on one condition.

    Args:
        labels: 0 for cover, 1 for stego.
        scores: Detector probabilities (higher = more likely stego).
        threshold: Decision threshold chosen on validation (never on test).
        bootstrap_resamples: If positive, add 95% CIs for ROC-AUC and P_E.
        seed: Bootstrap RNG seed.

    Returns:
        JSON-safe metric dictionary.
    """
    predictions = (scores >= threshold).astype(np.int64)
    metrics: dict[str, object] = {
        "sample_count": int(labels.size),
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(labels, scores)),
        "p_e": minimum_detection_error(labels, scores)[0],
        "tpr_at_1pct_fpr": tpr_at_fpr(labels, scores),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
        "threshold": float(threshold),
    }
    if bootstrap_resamples > 0:
        intervals = bootstrap_confidence_intervals(
            labels, scores, bootstrap_resamples=bootstrap_resamples, seed=seed
        )
        metrics["roc_auc_ci95"] = intervals["roc_auc"]
        metrics["p_e_ci95"] = intervals["p_e"]
    return metrics


def weighted_scores(
    scores: Mapping[str, NDArray[np.float64]], weights: Mapping[str, float]
) -> NDArray[np.float64]:
    """Weighted mean of detector probabilities (weights need not sum to one)."""
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("At least one ensemble weight must be positive.")
    combined = sum(scores[name] * weight for name, weight in weights.items())
    return np.asarray(combined, dtype=np.float64) / total


def fit_ensemble_weights(
    labels: NDArray[np.int64],
    scores: Mapping[str, NDArray[np.float64]],
    first: str,
    second: str,
) -> dict[str, object]:
    """Choose ``w`` in ``w·first + (1−w)·second`` by validation ROC-AUC.

    A one-parameter grid search is easy to explain and cannot overfit the way
    a flexible stacker can; ties prefer the more balanced weight. Operating
    thresholds come from the same validation scores.
    """
    best_weight = 0.5
    best_auc = -1.0
    for weight in WEIGHT_GRID:
        combined = weighted_scores(scores, {first: float(weight), second: float(1 - weight)})
        auc = float(roc_auc_score(labels, combined))
        closer_to_half = abs(weight - 0.5) < abs(best_weight - 0.5)
        if auc > best_auc + 1e-9 or (abs(auc - best_auc) <= 1e-9 and closer_to_half):
            best_auc, best_weight = auc, float(weight)
    weights = {first: best_weight, second: round(1 - best_weight, 2)}
    combined = weighted_scores(scores, weights)
    return {
        "method": "validation-weighted average",
        "weights": weights,
        "thresholds": select_operating_thresholds(labels, combined),
        "validation_roc_auc": best_auc,
        "validation_p_e": minimum_detection_error(labels, combined)[0],
    }


def statistical_score_from_features(features: NDArray[np.float32]) -> float:
    """Reproduce the untrained statistical detector from a feature vector.

    The fallback averages the chi-square p-value, RS estimate and SPA
    estimate. For grayscale images the "mean" block of the feature vector
    holds exactly those per-channel values (indices 1, 3, 4; index 1 is the
    log p-value), so no second pass over the image is needed.
    """
    p_value = float(np.exp(features[1]))
    rs_estimate = float(features[3])
    spa_estimate = float(features[4])
    return float(np.clip((p_value + rs_estimate + spa_estimate) / 3.0, 0.0, 1.0))
