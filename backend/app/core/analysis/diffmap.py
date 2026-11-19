"""Amplified absolute-difference maps for visualizing embedding changes."""

import numpy as np
from numpy.typing import NDArray


def amplified_difference(
    cover: NDArray[np.uint8],
    stego: NDArray[np.uint8],
    amplification: int = 50,
) -> NDArray[np.uint8]:
    """Return clipped absolute pixel differences multiplied by an integer factor."""
    if cover.dtype != np.uint8 or stego.dtype != np.uint8:
        raise ValueError("Cover and stego arrays must use uint8 samples.")
    if cover.shape != stego.shape or cover.ndim not in {2, 3}:
        raise ValueError("Cover and stego arrays must have matching 2D or 3D shapes.")
    if cover.ndim == 3 and cover.shape[2] != 3:
        raise ValueError("RGB images must have exactly three channels.")
    if amplification < 0:
        raise ValueError("Amplification must be non-negative.")
    difference = np.abs(cover.astype(np.int16) - stego.astype(np.int16)).astype(np.int32)
    amplified = difference * amplification
    np.minimum(amplified, 255, out=amplified)
    return np.asarray(amplified, dtype=np.uint8)
