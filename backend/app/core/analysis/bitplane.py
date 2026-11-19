"""Bit-plane extraction helpers for visualizing image sample bits."""

import numpy as np
from numpy.typing import NDArray


def extract_bitplane(image: NDArray[np.uint8], plane: int = 0) -> NDArray[np.uint8]:
    """Return a selected bit plane scaled to black (0) and white (255)."""
    if image.dtype != np.uint8:
        raise ValueError("Image array must use uint8 samples.")
    if not 0 <= plane <= 7:
        raise ValueError("Bit-plane index must be between 0 and 7.")
    if image.ndim not in {2, 3} or (image.ndim == 3 and image.shape[2] != 3):
        raise ValueError("Image array must have shape (H, W) or (H, W, 3).")
    return (((image >> plane) & 1) * 255).astype(np.uint8)
