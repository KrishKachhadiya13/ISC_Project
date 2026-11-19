"""Tests for Phase 6 StegNet-Lite inference, training helpers, and explanations."""

import io
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from app.steganalysis.deep.calibration import calibrated_probabilities, fit_temperature
from app.steganalysis.deep.filters import KV_KERNEL, KVFilter
from app.steganalysis.deep.gradcam import gradcam_map, residual_energy_map
from app.steganalysis.deep.infer import (
    explain_image,
    infer_image,
    load_cnn_checkpoint,
)
from app.steganalysis.deep.model import build_model
from app.steganalysis.deep.train import (
    bootstrap_confidence_intervals,
    calculate_metrics,
    minimum_detection_error,
    save_checkpoint,
)


def test_kv_filter_matches_reference_kernel_and_is_frozen() -> None:
    """Fixed high-pass weights match the blueprint and residuals are truncated."""
    layer = KVFilter(truncation=0.25)
    assert torch.equal(layer.conv.weight.detach()[0, 0], KV_KERNEL)
    assert not layer.conv.weight.requires_grad

    output = layer(torch.randn(2, 1, 16, 16))

    assert tuple(output.shape) == (2, 1, 16, 16)
    assert float(output.abs().max()) <= 0.25
    with pytest.raises(ValueError, match="positive"):
        KVFilter(truncation=0)


def test_stegnet_lite_forward_is_small_and_returns_one_logit_per_image() -> None:
    """The specified network has one binary logit and fewer than two million weights."""
    model = build_model()
    model.eval()

    with torch.inference_mode():
        logits = model(torch.rand(2, 1, 256, 256))

    assert logits.shape == (2,)
    assert model.trainable_parameter_count() < 2_000_000
    assert not model.kv_filter.conv.weight.requires_grad
    with pytest.raises(ValueError, match="at least 32"):
        model(torch.rand(1, 1, 16, 16))


def test_inference_supports_256_large_and_rgb_images() -> None:
    """Inference handles a single tile, an even grid, and RGB channel aggregation."""
    model = build_model()
    gray = np.zeros((256, 256), dtype=np.uint8)
    large = np.zeros((512, 768), dtype=np.uint8)
    rgb = np.zeros((256, 256, 3), dtype=np.uint8)

    single = infer_image(model, gray)
    tiled = infer_image(model, large)
    color = infer_image(model, rgb)

    assert single.tiles_per_channel == 1
    assert tiled.tiles_per_channel == 6
    assert len(color.channel_logits) == 3
    assert color.logit == pytest.approx(color.max_logit)
    assert color.probability == pytest.approx(0.5)
    with pytest.raises(ValueError, match="at least 256"):
        infer_image(model, np.zeros((255, 256), dtype=np.uint8))
    with pytest.raises(ValueError, match="uint8"):
        infer_image(model, np.zeros((256, 256), dtype=np.float32))  # type: ignore[arg-type]


def test_gradcam_and_residual_energy_return_input_sized_pngs() -> None:
    """Both explainers produce finite input-sized maps and valid PNG outputs."""
    model = build_model().eval()
    image = torch.rand(1, 1, 256, 256)
    cam = gradcam_map(model, image)
    residual = residual_energy_map(model, image)
    explanation = explain_image(
        model,
        np.asarray(image[0, 0].mul(255).byte(), dtype=np.uint8),
    )

    assert tuple(cam.shape) == (256, 256)
    assert tuple(residual.shape) == (256, 256)
    assert torch.isfinite(cam).all() and 0 <= float(cam.min()) <= float(cam.max()) <= 1
    assert torch.isfinite(residual).all()
    for data in (explanation.gradcam_png, explanation.residual_energy_png):
        with Image.open(io.BytesIO(data)) as heatmap:
            assert heatmap.format == "PNG"
            assert heatmap.size == (256, 256)


def test_checkpoint_round_trip_preserves_logits_and_temperature(tmp_path: Path) -> None:
    """Saving/loading a CNN checkpoint leaves deterministic logits unchanged."""
    model = build_model().eval()
    inputs = torch.rand(2, 1, 256, 256)
    with torch.inference_mode():
        expected = model(inputs)
    checkpoint_path = tmp_path / "cnn_v1.pt"
    save_checkpoint(
        model,
        checkpoint_path,
        temperature=1.7,
        metadata={"seed": 12},
    )

    loaded, temperature = load_cnn_checkpoint(checkpoint_path)
    with torch.inference_mode():
        actual = loaded(inputs)

    torch.testing.assert_close(actual, expected, rtol=0, atol=0)
    assert temperature == 1.7
    with pytest.raises(FileNotFoundError, match="not found"):
        load_cnn_checkpoint(tmp_path / "missing.pt")


def test_temperature_and_steganalysis_metrics_are_finite() -> None:
    """Validation calibration and test metrics include P_E and low-FPR TPR."""
    labels = np.array([0, 0, 0, 1, 1, 1], dtype=np.int64)
    logits = np.array([-2.0, -1.0, -0.5, 0.5, 1.0, 2.0], dtype=np.float64)
    temperature = fit_temperature(logits, labels)
    probabilities = calibrated_probabilities(logits, temperature)
    pe, threshold = minimum_detection_error(labels, logits)
    metrics = calculate_metrics(
        labels,
        logits,
        temperature=temperature,
        threshold=threshold,
        bootstrap_resamples=20,
        seed=3,
    )

    assert 0.05 <= temperature <= 20.0
    assert probabilities.shape == logits.shape
    assert 0 <= pe <= 0.5
    assert metrics["accuracy"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert set(metrics["bootstrap_95_ci"]) == {"roc_auc", "p_e"}
    assert (
        len(
            bootstrap_confidence_intervals(labels, logits, bootstrap_resamples=5, seed=3)["roc_auc"]
        )
        == 2
    )
    with pytest.raises(ValueError, match="both classes"):
        fit_temperature(np.array([1.0, 2.0]), np.array([1, 1]))
