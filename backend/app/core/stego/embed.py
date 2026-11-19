"""Stego stream embedding for sequential and passphrase-keyed modes."""

import os
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from app.core.stego import adaptive, lsb_match, lsb_replace
from app.core.stego.bitops import bytes_to_bits
from app.core.stego.exceptions import CapacityExceededError, UnsupportedImageError
from app.core.stego.header import HEADER_BITS, encode_header
from app.core.stego.keystream import chacha20_keystream
from app.core.stego.scatter import (
    MAX_PERMUTATION_SAMPLES,
    derive_stego_keys,
    expand_stego_key,
    permutation,
)

EmbeddingMethod = Literal["lsb_replace", "lsb_match", "lsb2_replace", "suniward", "hill"]
# Bits written per selected sample by each method (extraction needs to know this).
BITS_PER_SAMPLE: dict[str, int] = {
    "lsb_replace": 1,
    "lsb_match": 1,
    "lsb2_replace": 2,
    "suniward": 1,
    "hill": 1,
}
EmbeddingMode = Literal["keyed", "sequential"]
KEYED_SALT_BITS = 128
MAX_EMBED_PIXELS = 4_000_000


def maximum_payload_bytes(
    sample_count: int,
    mode: EmbeddingMode = "keyed",
    bits_per_sample: int = 1,
    method: EmbeddingMethod | None = None,
) -> int:
    """Return the largest byte payload that fits after reserving the header/salt.

    The 128 salt samples always hold one bit each; every remaining sample holds
    ``bits_per_sample`` bits.
    """
    if sample_count < 0:
        raise ValueError("Sample count must be non-negative.")
    if mode not in {"keyed", "sequential"}:
        raise ValueError(f"Unsupported embedding mode: {mode}.")
    if method in {"suniward", "hill"}:
        available_samples = sample_count - (KEYED_SALT_BITS if mode == "keyed" else 0)
        # pySTC uses the first 64 coding elements to carry its 32-bit message length.
        return max(0, (available_samples - 64 - HEADER_BITS) // 8)
    if mode == "keyed":
        available_bits = sample_count - KEYED_SALT_BITS
    elif mode == "sequential":
        available_bits = sample_count
    else:
        raise ValueError(f"Unsupported embedding mode: {mode}.")
    return max(0, (available_bits * bits_per_sample - HEADER_BITS) // 8)


def embed(
    cover: NDArray[np.uint8],
    payload: bytes,
    *,
    method: EmbeddingMethod = "lsb_replace",
    mode: EmbeddingMode = "keyed",
    stego_passphrase: str | None = None,
    stego_salt: bytes | None = None,
    matching_randomness: bytes | None = None,
    stego_key: bytes | None = None,
) -> NDArray[np.uint8]:
    """Embed opaque bytes in a grayscale or RGB uint8 image.

    Args:
        cover: C-order grayscale or RGB cover samples.
        payload: Packet bytes to store after the fixed stream header.
        method: LSB replacement or ±1 LSB matching.
        mode: Keyed ChaCha20 scatter or educational sequential placement.
        stego_passphrase: Required for keyed mode.
        stego_salt: Optional fixed salt for deterministic offline dataset generation.
        matching_randomness: Optional fair coins for deterministic offline generation.
        stego_key: Optional pre-derived 32-byte key that replaces the Argon2id step. For
            offline training-data generation only; never used for live messages.

    Returns:
        A new image array containing the embedded stream.

    Raises:
        CapacityExceededError: If the payload is larger than the image capacity.
        ValueError: If parameters or image shape are invalid.
        UnsupportedImageError: If the image exceeds the safe embed/permutation limits.
    """
    _validate_image(cover)
    if method not in BITS_PER_SAMPLE:
        raise ValueError(f"Unsupported embedding method: {method}.")
    if mode not in {"keyed", "sequential"}:
        raise ValueError(f"Unsupported embedding mode: {mode}.")

    samples = cover.reshape(-1)
    sample_count = samples.size
    if cover.shape[0] * cover.shape[1] > MAX_EMBED_PIXELS:
        raise UnsupportedImageError("Image exceeds the 4-megapixel embedding limit.")
    if mode == "keyed" and sample_count - KEYED_SALT_BITS > MAX_PERMUTATION_SAMPLES:
        raise UnsupportedImageError("Image exceeds the safe keyed permutation limit.")

    bits_per_sample = BITS_PER_SAMPLE[method]
    maximum = maximum_payload_bytes(sample_count, mode, bits_per_sample, method)
    minimum_samples = HEADER_BITS + (KEYED_SALT_BITS if mode == "keyed" else 0)
    if sample_count < minimum_samples or len(payload) > maximum:
        raise CapacityExceededError(maximum)
    stream = encode_header(len(payload)) + payload
    stream_bits = bytes_to_bits(stream)

    if mode == "sequential":
        if method in {"suniward", "hill"}:
            positions = np.arange(sample_count, dtype=np.int64)
            return adaptive.embed_adaptive(
                cover,
                stream,
                adaptive_method(method),
                positions,
            )
        positions = np.arange(stream_bits.size // bits_per_sample, dtype=np.int64)
        return _embed_samples(
            samples,
            positions,
            stream_bits,
            method,
            matching_randomness,
        ).reshape(cover.shape)

    if stego_key is None and (stego_passphrase is None or len(stego_passphrase) < 8):
        raise ValueError("Keyed mode requires a passphrase of at least 8 characters.")
    salt = stego_salt if stego_salt is not None else os.urandom(KEYED_SALT_BITS // 8)
    if len(salt) != KEYED_SALT_BITS // 8:
        raise ValueError("Stego salt must be exactly 16 bytes.")
    if stego_key is not None:
        position_key, whitening_key = expand_stego_key(stego_key, salt)
    else:
        assert stego_passphrase is not None  # checked above
        position_key, whitening_key = derive_stego_keys(stego_passphrase, salt)
    if method in {"suniward", "hill"}:
        sample_positions = KEYED_SALT_BITS + permutation(
            position_key, sample_count - KEYED_SALT_BITS
        )
        result = adaptive.embed_adaptive(
            cover,
            _xor_stream(stream, whitening_key),
            adaptive_method(method),
            sample_positions,
        )
        flat_result = result.reshape(-1)
        salt_positions = np.arange(KEYED_SALT_BITS, dtype=np.int64)
        flat_result = lsb_replace.embed_bits(flat_result, salt_positions, bytes_to_bits(salt))
        return flat_result.reshape(cover.shape)
    whitened = _xor_stream(stream, whitening_key)
    bits = bytes_to_bits(whitened)
    sample_positions = KEYED_SALT_BITS + permutation(position_key, sample_count - KEYED_SALT_BITS)

    result = samples.copy()
    salt_positions = np.arange(KEYED_SALT_BITS, dtype=np.int64)
    result = lsb_replace.embed_bits(result, salt_positions, bytes_to_bits(salt))
    result = _embed_samples(
        result,
        sample_positions[: bits.size // bits_per_sample],
        bits,
        method,
        matching_randomness,
    )
    return result.reshape(cover.shape)


def _validate_image(image: NDArray[np.uint8]) -> None:
    """Reject invalid array types and channel layouts before flattening."""
    if image.dtype != np.uint8:
        raise ValueError("Image array must use uint8 samples.")
    if image.ndim not in {2, 3} or (image.ndim == 3 and image.shape[2] != 3):
        raise ValueError("Image array must have shape (H, W) or (H, W, 3).")
    if image.shape[0] == 0 or image.shape[1] == 0:
        raise ValueError("Image dimensions must be non-empty.")


def adaptive_method(method: EmbeddingMethod) -> adaptive.AdaptiveMethod:
    """Return the narrowed adaptive scheme after its caller checks the method family."""
    if method not in {"suniward", "hill"}:
        raise ValueError(f"Unsupported adaptive embedding method: {method}.")
    return method


def _embed_samples(
    samples: NDArray[np.uint8],
    positions: NDArray[np.int64],
    bits: NDArray[np.uint8],
    method: EmbeddingMethod,
    matching_randomness: bytes | None = None,
) -> NDArray[np.uint8]:
    """Apply the selected bit-writing method to a flattened sample array."""
    if method == "lsb_replace":
        return lsb_replace.embed_bits(samples, positions, bits)
    if method == "lsb2_replace":
        return lsb_replace.embed_bits(samples, positions, bits, bits_per_sample=2)
    return lsb_match.embed_bits(
        samples,
        positions,
        bits,
        random_bytes=matching_randomness,
    )


def _xor_stream(data: bytes, key: bytes) -> bytes:
    """Whiten or unwhiten the stream with a zero-nonce ChaCha20 keystream."""
    pad = chacha20_keystream(key, len(data))
    return bytes(left ^ right for left, right in zip(data, pad, strict=True))
