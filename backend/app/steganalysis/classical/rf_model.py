"""Reproducible classical steganalysis model training and serialization."""

import json
import platform
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import sklearn
from numpy.typing import NDArray
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.steganalysis.classical.features import FEATURE_NAMES


@dataclass(frozen=True)
class ClassicalModels:
    """The primary Random Forest and secondary HistGradientBoosting models."""

    random_forest: RandomForestClassifier
    histogram_gradient_boosting: HistGradientBoostingClassifier


def train_classifiers(
    features: NDArray[np.float32],
    labels: NDArray[np.int8],
    seed: int,
    forest_trees: int = 300,
    hgb_iterations: int = 100,
) -> ClassicalModels:
    """Fit the Phase 5 primary RF and secondary HGB binary classifiers."""
    if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES):
        raise ValueError(f"Features must have shape (n, {len(FEATURE_NAMES)}).")
    if labels.ndim != 1 or labels.shape[0] != features.shape[0]:
        raise ValueError("Labels must be one-dimensional and match the feature rows.")
    if set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Training labels must include both cover (0) and stego (1).")
    if forest_trees < 1 or hgb_iterations < 1:
        raise ValueError("Model iteration counts must be positive.")
    if not np.isfinite(features).all():
        raise ValueError("Training features must be finite.")

    forest = RandomForestClassifier(
        n_estimators=forest_trees,
        n_jobs=-1,
        random_state=seed,
        class_weight="balanced",
    )
    histogram_boosting = HistGradientBoostingClassifier(
        max_iter=hgb_iterations,
        random_state=seed,
    )
    forest.fit(features, labels)
    histogram_boosting.fit(features, labels)
    return ClassicalModels(forest, histogram_boosting)


def classification_metrics(
    labels: NDArray[np.int8],
    predictions: NDArray[np.int8],
    probabilities: NDArray[np.float64],
) -> dict[str, object]:
    """Return standard binary metrics in a JSON-safe, finite representation."""
    if labels.ndim != 1 or predictions.shape != labels.shape or probabilities.shape != labels.shape:
        raise ValueError("Labels, predictions, and probabilities must have matching 1-D shapes.")
    if not labels.size or set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Evaluation labels must be non-empty and contain both classes.")
    if not np.isfinite(probabilities).all():
        raise ValueError("Predicted probabilities must be finite.")
    return {
        "sample_count": int(labels.size),
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
    }


def select_f1_threshold(
    labels: NDArray[np.int8],
    probabilities: NDArray[np.float64],
) -> float:
    """Choose the F1-maximizing binary threshold using validation predictions."""
    if labels.ndim != 1 or probabilities.shape != labels.shape or not labels.size:
        raise ValueError("Validation labels and probabilities must be non-empty matching vectors.")
    if set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Validation labels must include both cover (0) and stego (1).")
    if not np.isfinite(probabilities).all():
        raise ValueError("Validation probabilities must be finite.")
    unique_probabilities = np.unique(probabilities)
    midpoints = (unique_probabilities[:-1] + unique_probabilities[1:]) / 2.0
    candidates = np.unique(np.concatenate((unique_probabilities, midpoints, np.array([0.5]))))
    best_threshold = 0.5
    best_f1 = -1.0
    best_accuracy = -1.0
    for threshold in candidates:
        predictions = (probabilities >= threshold).astype(np.int8)
        candidate_f1 = float(f1_score(labels, predictions, zero_division=0))
        candidate_accuracy = float(accuracy_score(labels, predictions))
        if (candidate_f1, candidate_accuracy, -abs(float(threshold) - 0.5)) > (
            best_f1,
            best_accuracy,
            -abs(best_threshold - 0.5),
        ):
            best_threshold = float(threshold)
            best_f1 = candidate_f1
            best_accuracy = candidate_accuracy
    return best_threshold


def save_models(
    models: ClassicalModels,
    output: Path,
    *,
    training_data_sha256: str,
    seed: int,
    dataset_origin: str,
    experiment: dict[str, object],
) -> None:
    """Write model weights and JSON metadata beside each model."""
    output.mkdir(parents=True, exist_ok=True)
    common_metadata: dict[str, object] = {
        "format_version": 1,
        "feature_names": list(FEATURE_NAMES),
        "training_data_sha256": training_data_sha256,
        "dataset_origin": dataset_origin,
        "seed": seed,
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "experiment": experiment,
    }
    for model_name, model in (
        ("classical_rf", models.random_forest),
        ("classical_hgb", models.histogram_gradient_boosting),
    ):
        joblib.dump(model, output / f"{model_name}.joblib")
        metadata = {**common_metadata, "model": model_name}
        (output / f"{model_name}.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
