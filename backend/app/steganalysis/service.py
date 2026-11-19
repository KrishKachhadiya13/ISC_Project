"""Load available detectors once and score images with an honest breakdown.

The service works with whatever models exist in ``models/``:

* the rule-based statistical detector always runs and is labelled untrained;
* the trained classical model (Random Forest if present, else HistGradient-
  Boosting) runs when its joblib file and JSON sidecar exist;
* the CNN runs when ``cnn_v1.pt`` exists and the image is at least 256×256.

The final verdict comes from a validation-fitted ensemble configuration
(``models/ensemble.json``, written by ``scripts/evaluate.py``) when one
exists. Otherwise the strongest available trained detector decides at its
own validation-selected threshold, and the response says so.
"""

from __future__ import annotations

import base64
import json
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
from numpy.typing import NDArray

from app.steganalysis.classical.features import extract_features, statistical_fallback
from app.steganalysis.deep.calibration import calibrated_probabilities
from app.steganalysis.deep.infer import (
    TILE_SIZE,
    explain_image,
    infer_image,
    load_cnn_checkpoint,
)
from app.steganalysis.deep.model import StegNetLite
from app.steganalysis.registry import RegisteredModel, discover_models

DetectorName = Literal["statistical", "rf", "cnn"]
OperatingPointName = Literal["balanced", "low_false_alarm"]
ALL_DETECTORS: tuple[DetectorName, ...] = ("statistical", "rf", "cnn")
_CLASSICAL_THRESHOLD_KEYS = {
    "classical_rf": "random_forest",
    "classical_hgb": "histogram_gradient_boosting",
}


@dataclass
class ClassicalDetector:
    """A trained scikit-learn classifier and its validation threshold."""

    name: str
    model: Any
    threshold: float
    metadata: dict[str, object]


@dataclass
class CnnDetector:
    """A trained StegNet-Lite model, its temperature, and decision threshold."""

    model: StegNetLite
    temperature: float
    threshold: float
    metadata: dict[str, object]


@dataclass
class DetectorSuite:
    """All detectors that could be loaded from the model directory."""

    classical: ClassicalDetector | None = None
    cnn: CnnDetector | None = None
    ensemble: dict[str, Any] | None = None
    registered: tuple[RegisteredModel, ...] = ()
    load_warnings: list[str] = field(default_factory=list)

    def loaded_model_names(self) -> list[str]:
        """Return names of trained models that are ready for inference."""
        names: list[str] = []
        if self.classical is not None:
            names.append(self.classical.name)
        if self.cnn is not None:
            names.append("cnn_v1")
        return names


def load_detector_suite(models_dir: Path) -> DetectorSuite:
    """Discover and load every usable detector without failing the app.

    A broken or missing artifact disables only that detector; the reason is
    kept in ``load_warnings`` so the UI can show "not trained" honestly.
    """
    suite = DetectorSuite()
    try:
        suite.registered = discover_models(models_dir)
    except (OSError, ValueError) as exc:
        suite.load_warnings.append(f"Model discovery failed: {exc}")
        return suite
    by_name = {model.name: model for model in suite.registered}
    for name in ("classical_rf", "classical_hgb"):
        if name in by_name and suite.classical is None:
            suite.classical = _load_classical(by_name[name], suite.load_warnings)
    if "cnn_v1" in by_name:
        suite.cnn = _load_cnn(by_name["cnn_v1"], suite.load_warnings)
    suite.ensemble = _load_ensemble_config(Path(models_dir) / "ensemble.json", suite)
    return suite


def detect(
    suite: DetectorSuite,
    image: NDArray[np.uint8],
    *,
    detectors: tuple[DetectorName, ...] = ALL_DETECTORS,
    operating_point: OperatingPointName = "balanced",
    explain: bool = True,
) -> dict[str, Any]:
    """Score one decoded image with the requested detectors.

    Args:
        suite: Loaded detectors.
        image: Grayscale ``(H, W)`` or RGB ``(H, W, 3)`` uint8 array.
        detectors: Which detector families to run.
        operating_point: ``balanced`` or ``low_false_alarm`` threshold policy.
        explain: Whether to produce CNN heatmaps (slower).

    Returns:
        A JSON-safe dictionary matching the ``/detect`` response schema.
    """
    started = time.perf_counter()
    warnings_out: list[str] = []
    if image.ndim == 3:
        warnings_out.append(
            "Detectors were trained on grayscale images; RGB channels are scored "
            "separately and results are less reliable."
        )
    breakdown: dict[str, dict[str, Any]] = {}
    features: dict[str, float] = {}

    if "statistical" in detectors:
        breakdown["statistical"], features = _run_statistical(image)
    if "rf" in detectors:
        breakdown["rf"] = _run_classical(suite, image)
    heatmaps: dict[str, str] = {}
    if "cnn" in detectors:
        breakdown["cnn"], heatmaps = _run_cnn(suite, image, explain, warnings_out)

    verdict = _decide(suite, breakdown, operating_point, warnings_out)
    return {
        **verdict,
        "detectors": breakdown,
        "features": features,
        "heatmap_gradcam_png_base64": heatmaps.get("gradcam"),
        "heatmap_residual_png_base64": heatmaps.get("residual"),
        "warnings": warnings_out,
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 1),
    }


def _run_statistical(image: NDArray[np.uint8]) -> tuple[dict[str, Any], dict[str, float]]:
    """Run chi-square, RS and SPA and average per-channel feature values."""
    result = statistical_fallback(image)
    channel_features: list[dict[str, float | int]] = result["features"]  # type: ignore[assignment]
    averaged = {
        name: float(np.mean([float(channel[name]) for channel in channel_features]))
        for name in channel_features[0]
    }
    entry = {
        "available": True,
        "trained": False,
        "model": "statistical (untrained)",
        "probability": float(result["probability"]),  # type: ignore[arg-type]
        "label": result["label"],
        "threshold": 0.5,
        "components": result["detectors"],
    }
    return entry, averaged


def _run_classical(suite: DetectorSuite, image: NDArray[np.uint8]) -> dict[str, Any]:
    """Score the hand-crafted feature vector with the trained classifier."""
    detector = suite.classical
    if detector is None:
        return {"available": False, "trained": False, "reason": "Classical model not trained."}
    vector = extract_features(image).reshape(1, -1)
    probability = float(detector.model.predict_proba(vector)[0, 1])
    return {
        "available": True,
        "trained": True,
        "model": detector.name,
        "probability": probability,
        "label": "suspected_stego" if probability >= detector.threshold else "clean",
        "threshold": detector.threshold,
    }


def _run_cnn(
    suite: DetectorSuite,
    image: NDArray[np.uint8],
    explain: bool,
    warnings_out: list[str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Run tiled CNN inference and, if requested, both heatmaps."""
    detector = suite.cnn
    if detector is None:
        return {"available": False, "trained": False, "reason": "CNN not trained."}, {}
    if image.shape[0] < TILE_SIZE or image.shape[1] < TILE_SIZE:
        warnings_out.append("CNN skipped: it needs images of at least 256×256 pixels.")
        return {"available": False, "trained": True, "reason": "Image smaller than 256×256."}, {}
    result = infer_image(detector.model, image, temperature=detector.temperature)
    entry = {
        "available": True,
        "trained": True,
        "model": "cnn_v1",
        "probability": result.probability,
        "label": "suspected_stego" if result.probability >= detector.threshold else "clean",
        "threshold": detector.threshold,
        "max_channel_logit": result.max_logit,
        "tiles_per_channel": result.tiles_per_channel,
    }
    heatmaps: dict[str, str] = {}
    if explain:
        explanation = explain_image(detector.model, image)
        heatmaps["gradcam"] = base64.b64encode(explanation.gradcam_png).decode("ascii")
        heatmaps["residual"] = base64.b64encode(explanation.residual_energy_png).decode("ascii")
    return entry, heatmaps


def _decide(
    suite: DetectorSuite,
    breakdown: dict[str, dict[str, Any]],
    operating_point: OperatingPointName,
    warnings_out: list[str],
) -> dict[str, Any]:
    """Choose the verdict from the ensemble config or the best trained detector."""
    trained = {
        name: entry["probability"]
        for name, entry in breakdown.items()
        if entry.get("available") and entry.get("trained")
    }
    ensemble = suite.ensemble
    if ensemble is not None and set(ensemble["weights"]) == set(trained):
        weights = ensemble["weights"]
        total = sum(weights.values())
        probability = sum(trained[name] * weights[name] for name in trained) / total
        threshold = float(ensemble["thresholds"][operating_point])
        source = "ensemble (validation-weighted)"
    else:
        candidates: list[str] = [name for name in ("cnn", "rf") if name in trained]
        if not candidates and "statistical" in breakdown:
            candidates = ["statistical"]
        primary = candidates[0] if candidates else None
        if primary is None:
            raise ValueError("At least one detector must be requested.")
        probability = breakdown[primary]["probability"]
        threshold = breakdown[primary]["threshold"]
        source = breakdown[primary]["model"]
        if operating_point != "balanced" or len(trained) > 1:
            warnings_out.append(
                "No validated ensemble is available for this detector set; the verdict "
                f"uses {source} at its own validation threshold."
            )
        if not trained:
            warnings_out.append(
                "No trained detector is available; the verdict is a rule-based "
                "statistical estimate."
            )
    return {
        "label": "suspected_stego" if probability >= threshold else "clean",
        "probability": float(probability),
        "threshold": float(threshold),
        "operating_point": operating_point,
        "decision_source": source,
    }


def _load_classical(model: RegisteredModel, load_warnings: list[str]) -> ClassicalDetector | None:
    """Load a joblib classifier and its validation-selected threshold."""
    try:
        with warnings.catch_warnings():
            # A version mismatch would make predictions untrustworthy, so fail loudly.
            warnings.simplefilter("error")
            estimator = joblib.load(model.artifact_path)
        experiment: Any = model.metadata.get("experiment", {})
        thresholds: Any = experiment["decision_thresholds_selected_on_validation"]
        threshold = float(thresholds[_CLASSICAL_THRESHOLD_KEYS[model.name]])
    except Exception as exc:  # noqa: BLE001 - any load failure disables only this model
        load_warnings.append(f"{model.name} could not be loaded: {type(exc).__name__}: {exc}")
        return None
    return ClassicalDetector(model.name, estimator, threshold, model.metadata)


def _load_cnn(model: RegisteredModel, load_warnings: list[str]) -> CnnDetector | None:
    """Load the CNN checkpoint and its validation threshold on the CPU."""
    try:
        network, temperature = load_cnn_checkpoint(model.artifact_path, device="cpu")
        selection: Any = model.metadata["validation_selection"]
        # The saved threshold is a raw logit chosen on validation; convert it to
        # the same calibrated-probability scale that inference reports.
        logit_threshold = float(selection["threshold"])
        threshold = float(calibrated_probabilities(np.asarray([logit_threshold]), temperature)[0])
    except Exception as exc:  # noqa: BLE001 - any load failure disables only this model
        load_warnings.append(f"cnn_v1 could not be loaded: {type(exc).__name__}: {exc}")
        return None
    return CnnDetector(network, temperature, threshold, model.metadata)


def _load_ensemble_config(path: Path, suite: DetectorSuite) -> dict[str, Any] | None:
    """Read the optional validation-fitted ensemble weights and thresholds."""
    if not path.is_file():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        weights = {str(key): float(value) for key, value in config["weights"].items()}
        thresholds = {
            key: float(config["thresholds"][key]) for key in ("balanced", "low_false_alarm")
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        suite.load_warnings.append(f"ensemble.json ignored: {exc}")
        return None
    if not weights or any(value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        suite.load_warnings.append("ensemble.json ignored: weights must be non-negative.")
        return None
    return {**config, "weights": weights, "thresholds": thresholds}
