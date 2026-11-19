"""Westfeld–Pfitzmann chi-square attacks for LSB replacement steganography."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.stats import chi2


@dataclass(frozen=True)
class ChiSquareResult:
    """Chi-square statistic and upper-tail probability for paired bins."""

    statistic: float
    degrees_of_freedom: int
    p_value: float
    pair_difference: float


@dataclass(frozen=True)
class ProgressiveChiSquareResult:
    """Chi-square result computed over a growing image row prefix."""

    end_row: int
    result: ChiSquareResult


def chi_square_attack(channel: NDArray[np.uint8]) -> ChiSquareResult:
    """Compare ``(2k, 2k+1)`` histogram pairs (Westfeld & Pfitzmann, 1999).

    LSB replacement tends to equalize each even/odd histogram pair. The returned
    upper-tail p-value is therefore the attack score, not a calibrated probability
    that an image is stego.

    Args:
        channel: Two-dimensional 8-bit grayscale or color-channel samples.

    Returns:
        Statistic, degrees of freedom, upper-tail probability, and normalized
        absolute pair imbalance.
    """
    samples = _validate_channel(channel)
    histogram = np.bincount(samples.reshape(-1), minlength=256).astype(np.float64)
    even = histogram[0::2]
    odd = histogram[1::2]
    expected = (even + odd) / 2.0
    active = expected > 0
    degrees = int(np.count_nonzero(active))
    if degrees == 0:
        return ChiSquareResult(0.0, 0, 1.0, 0.0)
    statistic = float(np.sum(np.square(even[active] - odd[active]) / expected[active]))
    p_value = float(chi2.sf(statistic, degrees))
    pair_difference = float(np.sum(np.abs(even - odd)) / max(1, samples.size))
    return ChiSquareResult(statistic, degrees, p_value, pair_difference)


def progressive_chi_square(
    channel: NDArray[np.uint8],
    row_step: int = 16,
) -> list[ProgressiveChiSquareResult]:
    """Run the Westfeld–Pfitzmann (1999) attack over increasing row prefixes.

    Args:
        channel: Two-dimensional 8-bit image channel.
        row_step: Number of rows between measurements. The final image row is
            always included, even when it is not an exact multiple of the step.

    Returns:
        Results ordered by their one-based ending row.
    """
    samples = _validate_channel(channel)
    if row_step < 1:
        raise ValueError("Row step must be positive.")
    row_ends = list(range(row_step, samples.shape[0] + 1, row_step))
    if not row_ends or row_ends[-1] != samples.shape[0]:
        row_ends.append(samples.shape[0])
    return [
        ProgressiveChiSquareResult(end_row, chi_square_attack(samples[:end_row]))
        for end_row in row_ends
    ]


def _validate_channel(channel: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Require a non-empty 2-D uint8 channel."""
    if channel.dtype != np.uint8:
        raise ValueError("Image channel must use uint8 samples.")
    if channel.ndim != 2 or not channel.size:
        raise ValueError("Image channel must be a non-empty two-dimensional array.")
    return channel
