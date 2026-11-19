"""CNN inference, checkpoint loading, and image tiling for StegNet-Lite."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor

from app.steganalysis.deep.calibration import calibrated_probabilities
from app.steganalysis.deep.gradcam import (
    gradcam_map,
    heatmap_png_bytes,
    residual_energy_map,
)
from app.steganalysis.deep.model import StegNetLite, build_model

TILE_SIZE = 256
MAX_TILES = 16


@dataclass(frozen=True)
class InferenceResult:
    """Calibrated image score and grayscale/RGB aggregation details."""

    logit: float
    max_logit: float
    probability: float
    label: str
    channel_logits: tuple[float, ...]
    tiles_per_channel: int


@dataclass(frozen=True)
class ExplanationResult:
    """PNG-encoded Grad-CAM and residual-energy maps for one image tile."""

    gradcam_png: bytes
    residual_energy_png: bytes


def load_cnn_checkpoint(
    path: Path, device: str | torch.device = "cpu"
) -> tuple[StegNetLite, float]:
    """Load a versioned StegNet-Lite checkpoint and its temperature."""
    checkpoint_path = Path(path)
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"CNN checkpoint not found: {checkpoint_path}")
    checkpoint: Any = torch.load(checkpoint_path, map_location=device, weights_only=True)
    if not isinstance(checkpoint, dict) or checkpoint.get("format_version") != 1:
        raise ValueError("Unsupported or invalid CNN checkpoint format.")
    truncation = checkpoint.get("truncation")
    temperature = checkpoint.get("temperature")
    state_dict = checkpoint.get("model_state_dict")
    if not isinstance(truncation, (int, float)) or not isinstance(temperature, (int, float)):
        raise ValueError("CNN checkpoint must include numeric truncation and temperature.")
    if not isinstance(state_dict, dict):
        raise ValueError("CNN checkpoint must include a model state dictionary.")
    model = build_model(float(truncation)).to(device)
    model.load_state_dict(state_dict, strict=True)
    model.eval()
    calibrated_probabilities(np.asarray([0.0]), float(temperature))
    return model, float(temperature)


def infer_image(
    model: StegNetLite,
    image: NDArray[np.uint8],
    *,
    temperature: float = 1.0,
    device: str | torch.device = "cpu",
) -> InferenceResult:
    """Score grayscale/RGB image tiles and aggregate logits per channel.

    Images smaller than 256 pixels in either dimension are rejected. Larger
    images use up to 16 evenly spaced, non-overlapping 256×256 tiles.
    """
    channels = _validate_image(image)
    model = model.to(device)
    model.eval()
    per_channel: list[float] = []
    for channel in channels:
        tiles = _extract_tiles(channel)
        tensor = _tiles_to_tensor(tiles).to(device)
        with torch.inference_mode():
            logits = model(tensor)
        per_channel.append(float(logits.mean().item()))
    mean_logit = float(np.mean(per_channel))
    max_logit = float(np.max(per_channel))
    probability = float(calibrated_probabilities(np.asarray([mean_logit]), temperature)[0])
    return InferenceResult(
        logit=mean_logit,
        max_logit=max_logit,
        probability=probability,
        label="suspected_stego" if probability >= 0.5 else "clean",
        channel_logits=tuple(per_channel),
        tiles_per_channel=len(_extract_tiles(channels[0])),
    )


def explain_image(
    model: StegNetLite,
    image: NDArray[np.uint8],
    *,
    device: str | torch.device = "cpu",
) -> ExplanationResult:
    """Generate Grad-CAM and residual-energy PNG heatmaps for the highest-logit tile."""
    channels = _validate_image(image)
    model = model.to(device)
    model.eval()
    candidates: list[tuple[float, NDArray[np.uint8]]] = []
    for channel in channels:
        for tile in _extract_tiles(channel):
            tensor = _tiles_to_tensor([tile]).to(device)
            with torch.inference_mode():
                score = float(model(tensor).item())
            candidates.append((score, tile))
    _, selected_tile = max(candidates, key=lambda candidate: candidate[0])
    tensor = _tiles_to_tensor([selected_tile]).to(device)
    return ExplanationResult(
        gradcam_png=heatmap_png_bytes(gradcam_map(model, tensor)),
        residual_energy_png=heatmap_png_bytes(residual_energy_map(model, tensor)),
    )


def _validate_image(image: NDArray[np.uint8]) -> list[NDArray[np.uint8]]:
    """Require a non-empty grayscale or RGB uint8 image at least 256×256."""
    if image.dtype != np.uint8:
        raise ValueError("CNN image must use uint8 samples.")
    if image.ndim == 2:
        channels = [image]
    elif image.ndim == 3 and image.shape[2] == 3:
        channels = [image[:, :, index] for index in range(3)]
    else:
        raise ValueError("CNN image must be a non-empty grayscale or RGB array.")
    if not image.size or image.shape[0] < TILE_SIZE or image.shape[1] < TILE_SIZE:
        raise ValueError("CNN detection requires images at least 256×256 pixels.")
    return channels


def _extract_tiles(channel: NDArray[np.uint8]) -> list[NDArray[np.uint8]]:
    """Select an evenly spaced grid of at most 16 non-overlapping image tiles."""
    height, width = channel.shape
    row_count = min(4, height // TILE_SIZE)
    column_count = min(4, width // TILE_SIZE)
    row_starts = np.linspace(0, height - TILE_SIZE, row_count, dtype=int)
    column_starts = np.linspace(0, width - TILE_SIZE, column_count, dtype=int)
    return [
        channel[row : row + TILE_SIZE, column : column + TILE_SIZE]
        for row in row_starts
        for column in column_starts
    ][:MAX_TILES]


def _tiles_to_tensor(tiles: list[NDArray[np.uint8]]) -> Tensor:
    """Normalize grayscale uint8 tiles to a contiguous NCHW float tensor."""
    array = np.stack(tiles).astype(np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(1)
