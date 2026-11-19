"""Validation-fitted detector stacking and operating-point selection."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_curve

OperatingPoint = Literal["balanced", "low_false_alarm"]


@dataclass(frozen=True)
class EnsembleStacker:
    """Logistic-regression combiner and its fixed detector feature order."""

    detector_names: tuple[str, ...]
    classifier: LogisticRegression


def fit_stacker(
    validation_scores: Mapping[str, NDArray[np.float64]],
    labels: NDArray[np.int64],
) -> EnsembleStacker:
    """Fit a score stacker using validation detector probabilities only."""
    if labels.ndim != 1 or labels.size < 2 or set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Validation labels must be a vector containing both classes.")
    names = tuple(sorted(validation_scores))
    if not names or any(not name for name in names):
        raise ValueError("At least one named detector score vector is required.")

    columns: list[NDArray[np.float64]] = []
    for name in names:
        scores = np.asarray(validation_scores[name], dtype=np.float64)
        if scores.shape != labels.shape:
            raise ValueError(f"Validation scores for {name!r} must match the label vector.")
        if not np.isfinite(scores).all() or np.any((scores < 0.0) | (scores > 1.0)):
            raise ValueError(f"Validation scores for {name!r} must be finite probabilities.")
        columns.append(scores)

    classifier = LogisticRegression(solver="liblinear", max_iter=1000, random_state=1337)
    classifier.fit(np.column_stack(columns), labels)
    return EnsembleStacker(names, classifier)


def ensemble_probability(
    detector_probabilities: Mapping[str, float],
    *,
    stacker: EnsembleStacker | None = None,
    weights: Mapping[str, float] | None = None,
) -> float:
    """Combine detector probabilities with a stacker or transparent weighted mean.

    Without a validation-fitted stacker, detectors receive equal weights unless
    explicit non-negative validation-derived weights are supplied.
    """
    names, values = _validated_probabilities(detector_probabilities)
    if stacker is not None:
        if names != stacker.detector_names:
            raise ValueError("Inference detector names must match the fitted stacker.")
        probability = stacker.classifier.predict_proba(values.reshape(1, -1))[0, 1]
        return float(probability)

    if weights is None:
        weight_values = np.ones(len(names), dtype=np.float64)
    else:
        if set(weights) != set(names):
            raise ValueError("Weights must be provided for exactly the available detectors.")
        weight_values = np.asarray([weights[name] for name in names], dtype=np.float64)
        if not np.isfinite(weight_values).all() or np.any(weight_values < 0.0):
            raise ValueError("Weights must be finite and non-negative.")
    total_weight = float(weight_values.sum())
    if total_weight <= 0.0:
        raise ValueError("At least one detector weight must be positive.")
    return float(np.dot(values, weight_values) / total_weight)


def select_operating_thresholds(
    labels: NDArray[np.int64],
    probabilities: NDArray[np.float64],
) -> dict[OperatingPoint, float]:
    """Select balanced and <=1% validation-FPR probability thresholds."""
    if labels.ndim != 1 or probabilities.shape != labels.shape or labels.size < 2:
        raise ValueError("Validation labels and probabilities must be matching vectors.")
    if set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Validation labels must contain both classes.")
    if not np.isfinite(probabilities).all() or np.any(
        (probabilities < 0.0) | (probabilities > 1.0)
    ):
        raise ValueError("Validation scores must be finite probabilities.")

    false_positive_rate, true_positive_rate, thresholds = roc_curve(labels, probabilities)
    finite = np.isfinite(thresholds)
    false_positive_rate = false_positive_rate[finite]
    true_positive_rate = true_positive_rate[finite]
    thresholds = thresholds[finite]
    if not thresholds.size:
        raise ValueError("No finite validation thresholds are available.")

    balanced_index = int(np.argmax(true_positive_rate - false_positive_rate))
    low_alarm_indices = np.flatnonzero(false_positive_rate <= 0.01)
    low_alarm_index = max(
        low_alarm_indices,
        key=lambda index: (true_positive_rate[index], thresholds[index]),
    )
    return {
        "balanced": float(thresholds[balanced_index]),
        "low_false_alarm": float(thresholds[low_alarm_index]),
    }


def predict_ensemble(
    detector_probabilities: Mapping[str, float],
    thresholds: Mapping[OperatingPoint, float],
    *,
    operating_point: OperatingPoint = "balanced",
    stacker: EnsembleStacker | None = None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, object]:
    """Return a JSON-safe ensemble decision and its detector breakdown."""
    if operating_point not in thresholds:
        raise ValueError(f"No validation threshold is available for {operating_point!r}.")
    threshold = thresholds[operating_point]
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("Operating threshold must be a finite probability.")
    probability = ensemble_probability(
        detector_probabilities,
        stacker=stacker,
        weights=weights,
    )
    return {
        "label": "suspected_stego" if probability >= threshold else "clean",
        "probability": probability,
        "detectors": dict(sorted(detector_probabilities.items())),
        "operating_point": operating_point,
        "threshold": float(threshold),
    }


def _validated_probabilities(
    scores: Mapping[str, float],
) -> tuple[tuple[str, ...], NDArray[np.float64]]:
    """Validate a single-image detector score mapping in stable key order."""
    names = tuple(sorted(scores))
    if not names or any(not name for name in names):
        raise ValueError("At least one named detector probability is required.")
    values = np.asarray([scores[name] for name in names], dtype=np.float64)
    if not np.isfinite(values).all() or np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("Detector scores must be finite probabilities.")
    return names, values
