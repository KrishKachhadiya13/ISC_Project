"""Tests for the detector service: model loading, thresholds, and verdicts."""

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from app.config import BACKEND_DIR
from app.steganalysis.deep.model import build_model
from app.steganalysis.deep.train import save_checkpoint
from app.steganalysis.service import detect, load_detector_suite


def _noise(shape: tuple[int, ...], seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, shape, dtype=np.uint8)


def _write_cnn(models: Path, logit_threshold: float, temperature: float) -> None:
    """Save an untrained (but structurally real) CNN with a sidecar."""
    metadata = {"model": "cnn_v1", "validation_selection": {"threshold": logit_threshold}}
    save_checkpoint(
        build_model(3.0), models / "cnn_v1.pt", temperature=temperature, metadata=metadata
    )
    (models / "cnn_v1.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_empty_model_directory_uses_untrained_statistics(tmp_path: Path) -> None:
    """No models: only the statistical detector runs and the verdict says so."""
    suite = load_detector_suite(tmp_path / "missing")
    result = detect(suite, _noise((64, 64)))
    assert suite.loaded_model_names() == []
    assert result["decision_source"] == "statistical (untrained)"
    assert result["detectors"]["cnn"]["available"] is False
    assert 0.0 <= result["probability"] <= 1.0


def test_cnn_logit_threshold_is_converted_to_probability(tmp_path: Path) -> None:
    """A logit threshold of 2 with temperature 2 becomes sigmoid(1) ≈ 0.731."""
    _write_cnn(tmp_path, logit_threshold=2.0, temperature=2.0)
    suite = load_detector_suite(tmp_path)
    assert suite.cnn is not None
    assert suite.cnn.threshold == pytest.approx(1 / (1 + math.exp(-1.0)))


def test_cnn_runs_with_heatmaps_and_decides(tmp_path: Path) -> None:
    """With a CNN present it decides the verdict and returns both heatmaps."""
    _write_cnn(tmp_path, logit_threshold=0.0, temperature=1.0)
    suite = load_detector_suite(tmp_path)
    result = detect(suite, _noise((256, 256)), detectors=("statistical", "cnn"))
    assert result["decision_source"] == "cnn_v1"
    assert result["detectors"]["cnn"]["available"] is True
    assert result["heatmap_gradcam_png_base64"]
    assert result["heatmap_residual_png_base64"]


def test_cnn_skips_small_images_with_a_warning(tmp_path: Path) -> None:
    """Images under 256×256 are refused by the CNN but still scanned classically."""
    _write_cnn(tmp_path, logit_threshold=0.0, temperature=1.0)
    suite = load_detector_suite(tmp_path)
    result = detect(suite, _noise((100, 100)))
    assert result["detectors"]["cnn"]["available"] is False
    assert any("256×256" in warning for warning in result["warnings"])


def test_broken_artifact_disables_only_that_model(tmp_path: Path) -> None:
    """A corrupt checkpoint is reported, not fatal."""
    (tmp_path / "cnn_v1.pt").write_bytes(b"not a checkpoint")
    (tmp_path / "cnn_v1.json").write_text('{"model": "cnn_v1"}', encoding="utf-8")
    suite = load_detector_suite(tmp_path)
    assert suite.cnn is None
    assert any("cnn_v1 could not be loaded" in warning for warning in suite.load_warnings)


def test_ensemble_config_is_used_when_detectors_match(tmp_path: Path) -> None:
    """A validation-fitted ensemble.json decides when its detector set is available."""
    source = BACKEND_DIR / "models"
    if not (source / "classical_hgb.joblib").is_file():
        pytest.skip("classical_hgb model not present")
    for name in ("classical_hgb.joblib", "classical_hgb.json"):
        shutil.copy(source / name, tmp_path / name)
    _write_cnn(tmp_path, logit_threshold=0.0, temperature=1.0)
    config = {
        "weights": {"rf": 1.0, "cnn": 1.0},
        "thresholds": {"balanced": 0.5, "low_false_alarm": 0.9},
    }
    (tmp_path / "ensemble.json").write_text(json.dumps(config), encoding="utf-8")
    suite = load_detector_suite(tmp_path)
    image = _noise((256, 256))
    balanced = detect(suite, image, detectors=("rf", "cnn"), explain=False)
    strict = detect(
        suite, image, detectors=("rf", "cnn"), operating_point="low_false_alarm", explain=False
    )
    assert balanced["decision_source"].startswith("ensemble")
    assert balanced["threshold"] == 0.5 and strict["threshold"] == 0.9
    expected = (
        balanced["detectors"]["rf"]["probability"] + balanced["detectors"]["cnn"]["probability"]
    ) / 2
    assert balanced["probability"] == pytest.approx(expected)


def test_invalid_ensemble_config_is_ignored(tmp_path: Path) -> None:
    """Negative weights are rejected with a warning."""
    config = {"weights": {"rf": -1.0}, "thresholds": {"balanced": 0.5, "low_false_alarm": 0.9}}
    (tmp_path / "ensemble.json").write_text(json.dumps(config), encoding="utf-8")
    suite = load_detector_suite(tmp_path)
    assert suite.ensemble is None
    assert suite.load_warnings
