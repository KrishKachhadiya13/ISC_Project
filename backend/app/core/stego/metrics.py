"""Image quality metrics for comparing a cover with its stego output."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from skimage.metrics import structural_similarity

from app.core.analysis.diffmap import amplified_difference


@dataclass(frozen=True)
class StegoMetrics:
    """Quality and payload measurements for one embedding operation."""

    mse: float
    psnr: float
    ssim: float
    fraction_changed: float
    embedded_bits: int
    bpp: float
    difference_map: NDArray[np.uint8]


def calculate_metrics(
    cover: NDArray[np.uint8],
    stego: NDArray[np.uint8],
    embedded_bits: int,
) -> StegoMetrics:
    """Calculate MSE, PSNR, SSIM, changed fraction, bpp, and difference map."""
    if cover.dtype != np.uint8 or stego.dtype != np.uint8:
        raise ValueError("Cover and stego arrays must use uint8 samples.")
    if cover.shape != stego.shape or cover.ndim not in {2, 3}:
        raise ValueError("Cover and stego arrays must have matching 2D or 3D shapes.")
    if cover.ndim == 3 and cover.shape[2] != 3:
        raise ValueError("RGB images must have exactly three channels.")
    if min(cover.shape[:2]) < 7:
        raise ValueError("Images must be at least 7x7 for SSIM.")
    if embedded_bits < 0:
        raise ValueError("Embedded bit count must be non-negative.")

    difference = cover.astype(np.float64) - stego.astype(np.float64)
    mse = float(np.mean(np.square(difference)))
    psnr = float("inf") if mse == 0 else float(10.0 * np.log10((255.0**2) / mse))
    ssim = float(
        structural_similarity(  # type: ignore[no-untyped-call]
            cover, stego, data_range=255, channel_axis=-1 if cover.ndim == 3 else None
        )
    )
    changed = np.count_nonzero(cover != stego) / cover.size
    bpp = embedded_bits / (cover.shape[0] * cover.shape[1])
    return StegoMetrics(
        mse=mse,
        psnr=psnr,
        ssim=ssim,
        fraction_changed=float(changed),
        embedded_bits=embedded_bits,
        bpp=float(bpp),
        difference_map=amplified_difference(cover, stego),
    )
