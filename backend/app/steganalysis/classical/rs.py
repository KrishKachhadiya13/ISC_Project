"""RS analysis for LSB steganography (Fridrich, Goljan & Du, 2001)."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class RSResult:
    """Regular/singular group counts and estimated embedding rate."""

    r_m: int
    s_m: int
    r_neg_m: int
    s_neg_m: int
    estimated_rate: float
    group_count: int


def rs_analysis(channel: NDArray[np.uint8]) -> RSResult:
    """Estimate LSB replacement rate from groups of four adjacent samples.

    The discrimination function is the sum of absolute differences between
    consecutive samples. Mask ``[0, 1, 1, 0]`` and its negative are applied to
    each group; the quadratic intersection estimate follows Fridrich, Goljan &
    Du (2001). Counts are reported from the ordinary (non-inverted) image.

    Args:
        channel: Two-dimensional 8-bit image channel.

    Returns:
        Four R/S counts, a bounded embedding-rate estimate, and group count.
    """
    if channel.dtype != np.uint8:
        raise ValueError("Image channel must use uint8 samples.")
    if channel.ndim != 2 or not channel.size:
        raise ValueError("Image channel must be a non-empty two-dimensional array.")

    height, width = channel.shape
    block_height, block_width = height // 2, width // 2
    if block_height == 0 or block_width < 2:
        return RSResult(0, 0, 0, 0, 0.0, 0)
    blocks = (
        channel[: block_height * 2, : block_width * 2]
        .reshape(block_height, 2, block_width, 2)
        .transpose(0, 2, 1, 3)
        .reshape(-1, 4)
        .astype(np.int16)
    )
    mask = np.array([0, 1, 1, 0], dtype=np.int16)
    positive = _classify(blocks, mask)
    negative = _classify(blocks, -mask)

    inverted = blocks ^ 1
    positive_inverse = _classify(inverted, mask)
    negative_inverse = _classify(inverted, -mask)
    estimate = _estimate_rate(
        positive,
        negative,
        positive_inverse,
        negative_inverse,
        int(blocks.shape[0]),
    )
    return RSResult(
        r_m=positive[0],
        s_m=positive[1],
        r_neg_m=negative[0],
        s_neg_m=negative[1],
        estimated_rate=estimate,
        group_count=int(blocks.shape[0]),
    )


def _classify(
    groups: NDArray[np.int16],
    mask: NDArray[np.int16],
) -> tuple[int, int]:
    """Count regular and singular groups after a signed LSB mask flip."""
    original = _discrimination(groups)
    flipped = groups.copy()
    for column in (1, 2):
        even = (groups[:, column] & 1) == 0
        delta = np.where(mask[column] > 0, np.where(even, 1, -1), np.where(even, -1, 1))
        flipped[:, column] += delta
    changed = _discrimination(flipped)
    return int(np.count_nonzero(changed > original)), int(np.count_nonzero(changed < original))


def _discrimination(groups: NDArray[np.int16]) -> NDArray[np.int32]:
    """Return cyclic adjacent-sample variation for each four-sample group."""
    variation: NDArray[np.int32] = (
        np.abs(groups[:, 0] - groups[:, 1])
        + np.abs(groups[:, 1] - groups[:, 2])
        + np.abs(groups[:, 2] - groups[:, 3])
    ).astype(np.int32)
    return variation


def _estimate_rate(
    positive: tuple[int, int],
    negative: tuple[int, int],
    positive_inverse: tuple[int, int],
    negative_inverse: tuple[int, int],
    group_count: int,
) -> float:
    """Solve the standard RS quadratic and clamp its estimate to [0, 1]."""
    d0 = (positive[0] - positive[1]) / group_count
    dn0 = (negative[0] - negative[1]) / group_count
    d1 = (positive_inverse[0] - positive_inverse[1]) / group_count
    dn1 = (negative_inverse[0] - negative_inverse[1]) / group_count
    a = 2.0 * (d1 + d0)
    b = dn0 - dn1 - d1 - 3.0 * d0
    c = d0 - dn0
    if abs(a) < 1e-12:
        roots = [c / b] if abs(b) >= 1e-12 else []
    else:
        discriminant = b * b - 4.0 * a * c
        roots = (
            [
                (-b + np.sqrt(discriminant)) / (2.0 * a),
                (-b - np.sqrt(discriminant)) / (2.0 * a),
            ]
            if discriminant >= 0
            else []
        )
    if not roots:
        return 0.0
    intersection = min((float(root) for root in roots), key=abs)
    if abs(intersection - 0.5) < 1e-8:
        return 0.0
    return float(np.clip(intersection / (intersection - 0.5), 0.0, 1.0))
