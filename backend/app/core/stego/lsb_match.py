"""Vectorized ±1 LSB matching with unbiased cryptographic coin flips."""

import os

import numpy as np
from numpy.typing import NDArray

from app.core.stego.bitops import BitArray


def embed_bits(
    samples: NDArray[np.uint8],
    positions: NDArray[np.int64],
    bits: BitArray,
    random_bytes: bytes | None = None,
) -> NDArray[np.uint8]:
    """Match selected LSBs by changing mismatched samples by exactly one.

    Args:
        samples: Flattened uint8 image samples.
        positions: Sample indices corresponding to message bits.
        bits: Binary message bits.
        random_bytes: Optional pre-generated fair coins for reproducible offline
            dataset creation. Production calls should leave this unset.
    """
    if positions.size != bits.size:
        raise ValueError("Position and bit counts must match.")
    if np.any((bits != 0) & (bits != 1)):
        raise ValueError("Bits must contain only zero and one.")

    result = samples.copy()
    selected = result[positions]
    mismatch = (selected & 1) != bits
    count = int(np.count_nonzero(mismatch))
    if count == 0:
        return result

    mismatched_positions = positions[mismatch]
    values = result[mismatched_positions]
    if random_bytes is None:
        coin_bytes = os.urandom(count)
    elif len(random_bytes) < count:
        raise ValueError(f"Need at least {count} matching coin bytes.")
    else:
        coin_bytes = random_bytes[:count]
    fair_coins = np.frombuffer(coin_bytes, dtype=np.uint8) & 1
    direction = np.where(fair_coins == 0, -1, 1).astype(np.int16)
    direction = np.where(values == 0, 1, direction)
    direction = np.where(values == 255, -1, direction)
    result[mismatched_positions] = (values.astype(np.int16) + direction).astype(np.uint8)
    return result
