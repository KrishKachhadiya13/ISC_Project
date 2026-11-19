"""Sample Pair Analysis for LSB embedding-rate estimation."""

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class SPAResult:
    """SPA trace-set counts and estimated embedding rate."""

    x_count: int
    y_count: int
    w_count: int
    z_count: int
    pair_count: int
    estimated_rate: float


def sample_pair_analysis(channel: NDArray[np.uint8]) -> SPAResult:
    """Estimate LSB embedding rate using pair trace sets (Dumitrescu et al., 2002/2003).

    Horizontally adjacent samples are assigned to X/Y trace sets and the
    standard SPA quadratic is solved under its cover-image symmetry assumption.
    The result is a statistical estimate, not proof of hidden data.

    Args:
        channel: Two-dimensional 8-bit grayscale or color-channel samples.

    Returns:
        Trace-set counts and an estimated rate bounded to ``[0, 1]``.
    """
    if channel.dtype != np.uint8:
        raise ValueError("Image channel must use uint8 samples.")
    if channel.ndim != 2 or not channel.size:
        raise ValueError("Image channel must be a non-empty two-dimensional array.")
    if channel.shape[1] < 2:
        return SPAResult(0, 0, 0, 0, 0, 0.0)

    left = channel[:, :-1].astype(np.int16).reshape(-1)
    right = channel[:, 1:].astype(np.int16).reshape(-1)
    right_even = (right & 1) == 0
    x_count = int(np.count_nonzero((right_even & (right > left)) | (~right_even & (right < left))))
    y_count = int(np.count_nonzero((right_even & (right < left)) | (~right_even & (right > left))))
    z_count = int(np.count_nonzero(left == right))
    same_bin = (left >> 1) == (right >> 1)
    w_count = int(np.count_nonzero(same_bin & (left != right)))
    rate = _solve_spa(x_count, y_count, w_count, z_count)
    return SPAResult(x_count, y_count, w_count, z_count, int(left.size), rate)


def _solve_spa(x_count: int, y_count: int, w_count: int, z_count: int) -> float:
    """Solve the Dumitrescu et al. quadratic, selecting the plausible root."""
    a = 0.5 * (w_count + z_count)
    b = 2.0 * x_count - (x_count + y_count + w_count + z_count)
    c = float(y_count - x_count)
    if abs(a) < 1e-12:
        if abs(b) < 1e-12:
            return 0.0
        roots = [-c / b]
    else:
        discriminant = b * b - 4.0 * a * c
        if discriminant < 0:
            return 0.0
        root = math.sqrt(discriminant)
        roots = [(-b + root) / (2.0 * a), (-b - root) / (2.0 * a)]
    plausible = [candidate for candidate in roots if 0 <= candidate <= 0.5]
    if not plausible:
        return 0.0
    embedding_fraction = min(plausible, key=abs)
    return float(np.clip(2.0 * embedding_fraction, 0.0, 1.0))
