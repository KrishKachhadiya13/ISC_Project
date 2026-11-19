"""Grad-CAM and residual-energy maps for StegNet-Lite explanations."""

from io import BytesIO

import matplotlib
import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image
from torch import Tensor
from torch.nn import functional as functional

from app.steganalysis.deep.model import StegNetLite

matplotlib.use("Agg")


def gradcam_map(model: StegNetLite, image: Tensor) -> Tensor:
    """Generate an input-sized Grad-CAM map from the last convolutional block."""
    if image.ndim != 4 or image.shape[0] != 1 or image.shape[1] != 1:
        raise ValueError("Grad-CAM requires one grayscale tensor shaped (1, 1, H, W).")
    activations: list[Tensor] = []
    handle = model.last_conv_layer.register_forward_hook(
        lambda _module, _inputs, output: activations.append(output)
    )
    try:
        model.eval()
        with torch.enable_grad():
            logits = model(image)
            if not activations:
                raise RuntimeError("Grad-CAM target layer did not produce an activation.")
            gradients = torch.autograd.grad(logits.sum(), activations[0])[0]
            weights = gradients.mean(dim=(2, 3), keepdim=True)
            cam = torch.relu((weights * activations[0]).sum(dim=1, keepdim=True))
            cam = functional.interpolate(
                cam,
                size=image.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
        return _normalize_map(cam.detach()).squeeze(0).squeeze(0)
    finally:
        handle.remove()


def residual_energy_map(model: StegNetLite, image: Tensor, window_size: int = 15) -> Tensor:
    """Return a normalized local mean of absolute, truncated KV residual energy."""
    if image.ndim != 4 or image.shape[0] != 1 or image.shape[1] != 1:
        raise ValueError("Residual-energy map requires one grayscale tensor shaped (1, 1, H, W).")
    if window_size < 1 or window_size % 2 == 0:
        raise ValueError("Residual-energy window size must be a positive odd integer.")
    with torch.no_grad():
        residual = model.kv_filter(image).abs()
        energy = functional.avg_pool2d(
            residual,
            kernel_size=window_size,
            stride=1,
            padding=window_size // 2,
            count_include_pad=False,
        )
    return _normalize_map(energy).squeeze(0).squeeze(0)


def heatmap_png_bytes(heatmap: Tensor | NDArray[np.float32]) -> bytes:
    """Encode a normalized scalar heatmap as an inferno-colored RGB PNG."""
    values = np.asarray(
        heatmap.detach().cpu().numpy() if isinstance(heatmap, Tensor) else heatmap,
        dtype=np.float32,
    )
    if values.ndim != 2 or not values.size or not np.isfinite(values).all():
        raise ValueError("Heatmap must be a non-empty finite two-dimensional array.")
    normalized = np.clip(values, 0.0, 1.0)
    rgb = matplotlib.colormaps["inferno"](normalized, bytes=True)[..., :3]
    output = BytesIO()
    Image.fromarray(rgb).save(output, format="PNG", optimize=True)
    return output.getvalue()


def _normalize_map(values: Tensor) -> Tensor:
    """Scale each spatial map to [0, 1], returning zeros for constant maps."""
    minimum = values.amin(dim=(-2, -1), keepdim=True)
    shifted = values - minimum
    maximum = shifted.amax(dim=(-2, -1), keepdim=True)
    return torch.where(maximum > 0, shifted / maximum.clamp_min(1e-12), torch.zeros_like(shifted))
