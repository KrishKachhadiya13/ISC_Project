"""Vectorized least-significant-bit replacement embedding."""

import numpy as np
from numpy.typing import NDArray

from app.core.stego.bitops import BitArray


def embed_bits(
    samples: NDArray[np.uint8],
    positions: NDArray[np.int64],
    bits: BitArray,
    bits_per_sample: int = 1,
) -> NDArray[np.uint8]:
    """Replace each selected sample's low ``bits_per_sample`` bits with message bits.

    With ``bits_per_sample=1`` this is classic LSB replacement. With 2, each
    selected sample carries two consecutive message bits (first bit in bit 1,
    second bit in bit 0), doubling capacity at the cost of larger changes
    (up to +-3 per sample instead of +-1).
    """
    if bits_per_sample not in (1, 2):
        raise ValueError("Bits per sample must be 1 or 2.")
    if positions.size * bits_per_sample != bits.size:
        raise ValueError("Position and bit counts must match (bits = positions x bits per sample).")
    if np.any((bits != 0) & (bits != 1)):
        raise ValueError("Bits must contain only zero and one.")
    result = samples.copy()
    mask = np.uint8((1 << bits_per_sample) - 1)
    symbols = bits.reshape(-1, bits_per_sample)
    # MSB-first: for k=2 the symbol is 2*first_bit + second_bit.
    values = symbols[:, 0] if bits_per_sample == 1 else (symbols[:, 0] << 1) | symbols[:, 1]
    result[positions] = (result[positions] & ~mask) | values.astype(np.uint8)
    return result


def read_bits(
    samples: NDArray[np.uint8],
    positions: NDArray[np.int64],
    bits_per_sample: int = 1,
) -> BitArray:
    """Read the bits written by ``embed_bits``, in the same MSB-first order."""
    if bits_per_sample not in (1, 2):
        raise ValueError("Bits per sample must be 1 or 2.")
    values = samples[positions] & np.uint8((1 << bits_per_sample) - 1)
    if bits_per_sample == 1:
        return values.astype(np.uint8)
    return np.stack(((values >> 1) & 1, values & 1), axis=1).reshape(-1).astype(np.uint8)
