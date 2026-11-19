"""Tests for Phase 7's model registry and validation-fitted ensemble helpers."""

import json
from pathlib import Path

import numpy as np
import pytest

from app.steganalysis.ensemble import (
    ensemble_probability,
    fit_stacker,
    predict_ensemble,
    select_operating_thresholds,
)
from app.steganalysis.registry import discover_models


def test_stacker_predicts_with_validation_fitted_detector_order() -> None:
    """A stacker accepts the same score channels used to fit it."""
    labels = np.array([0, 0, 0, 1, 1, 1], dtype=np.int64)
    validation = {
        "cnn": np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9]),
        "rf": np.array([0.2, 0.3, 0.4, 0.6, 0.7, 0.8]),
    }
    stacker = fit_stacker(validation, labels)

    probability = ensemble_probability({"rf": 0.75, "cnn": 0.85}, stacker=stacker)

    assert stacker.detector_names == ("cnn", "rf")
    assert probability > 0.5
    with pytest.raises(ValueError, match="names must match"):
        ensemble_probability({"cnn": 0.8}, stacker=stacker)


def test_weighted_average_and_operating_point_output() -> None:
    """The documented fallback averages scores and applies validation thresholds."""
    scores = {"cnn": 0.8, "rf": 0.4}
    assert ensemble_probability(scores) == pytest.approx(0.6)
    assert ensemble_probability(scores, weights={"cnn": 3.0, "rf": 1.0}) == pytest.approx(0.7)

    result = predict_ensemble(
        scores,
        {"balanced": 0.5, "low_false_alarm": 0.9},
        operating_point="balanced",
    )

    assert result == {
        "label": "suspected_stego",
        "probability": pytest.approx(0.6),
        "detectors": {"cnn": 0.8, "rf": 0.4},
        "operating_point": "balanced",
        "threshold": 0.5,
    }
    with pytest.raises(ValueError, match="exactly"):
        ensemble_probability(scores, weights={"cnn": 1.0})


def test_thresholds_use_validation_data_and_respect_low_false_alarm() -> None:
    """Selected thresholds maximize Youden J and cap validation FPR at one percent."""
    labels = np.array([0] * 100 + [1] * 100, dtype=np.int64)
    probabilities = np.concatenate((np.linspace(0.01, 0.8, 100), np.linspace(0.2, 0.99, 100)))

    thresholds = select_operating_thresholds(labels, probabilities)
    predictions = probabilities >= thresholds["low_false_alarm"]
    false_positive_rate = float(predictions[:100].mean())

    assert 0.0 <= thresholds["balanced"] <= 1.0
    assert false_positive_rate <= 0.01
    with pytest.raises(ValueError, match="both classes"):
        select_operating_thresholds(np.array([0, 0]), np.array([0.1, 0.2]))


def test_model_registry_discovers_only_complete_supported_pairs(tmp_path: Path) -> None:
    """Known sidecars are exposed only when matching weight files exist."""
    assert discover_models(tmp_path / "empty") == ()
    (tmp_path / "classical_rf.joblib").write_bytes(b"test artifact")
    (tmp_path / "classical_rf.json").write_text(
        json.dumps({"model": "classical_rf", "seed": 7}),
        encoding="utf-8",
    )
    (tmp_path / "model_card.json").write_text('{"title": "not a sidecar"}', encoding="utf-8")

    models = discover_models(tmp_path)

    assert len(models) == 1
    assert models[0].name == "classical_rf"
    assert models[0].artifact_path.name == "classical_rf.joblib"
    assert models[0].metadata["seed"] == 7


def test_model_registry_rejects_incomplete_or_mismatched_pairs(tmp_path: Path) -> None:
    """A half-written model pair cannot be silently treated as available."""
    (tmp_path / "cnn_v1.json").write_text('{"model": "cnn_v1"}', encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="artifact is missing"):
        discover_models(tmp_path)

    (tmp_path / "cnn_v1.pt").write_bytes(b"test artifact")
    (tmp_path / "cnn_v1.json").write_text('{"model": "other"}', encoding="utf-8")
    with pytest.raises(ValueError, match="must identify"):
        discover_models(tmp_path)
