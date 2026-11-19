"""MSB-first conversion helpers for byte-oriented stego streams."""

import numpy as np
from numpy.typing import NDArray

BitArray = NDArray[np.uint8]


def bytes_to_bits(data: bytes) -> BitArray:
    """Expand bytes into a uint8 bit vector in most-significant-bit-first order."""
    if not data:
        return np.empty(0, dtype=np.uint8)
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8), bitorder="big")


def bits_to_bytes(bits: BitArray) -> bytes:
    """Pack a binary uint8 vector into bytes using most-significant-bit-first order."""
    if bits.ndim != 1:
        raise ValueError("Bits must be a one-dimensional array.")
    if bits.size % 8:
        raise ValueError("Bit count must be divisible by 8.")
    if np.any((bits != 0) & (bits != 1)):
        raise ValueError("Bits must contain only zero and one.")
    return np.packbits(bits, bitorder="big").tobytes()
