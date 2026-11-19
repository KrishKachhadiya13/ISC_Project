"""Stego stream extraction with a uniform no-data error for invalid headers."""

from typing import Literal

import numpy as np
from numpy.typing import NDArray

from app.core.stego import lsb_replace
from app.core.stego.adaptive import extract_adaptive
from app.core.stego.bitops import bits_to_bytes
from app.core.stego.embed import KEYED_SALT_BITS, _validate_image, maximum_payload_bytes
from app.core.stego.exceptions import NoHiddenDataError
from app.core.stego.header import HEADER_BITS, HEADER_BYTES, decode_header
from app.core.stego.keystream import chacha20_keystream
from app.core.stego.scatter import derive_stego_keys, permutation

EmbeddingMode = Literal["keyed", "sequential"]
# Decoder codes to try in order; zero selects the adaptive STC framing.
AUTO_DETECT_ORDER = (1, 2, 0)


def extract_auto(
    stego: NDArray[np.uint8],
    *,
    mode: EmbeddingMode = "keyed",
    stego_passphrase: str | None = None,
) -> tuple[bytes, int]:
    """Try each decoder and return ``(payload, technique_code)`` for the first valid stream.

    A wrong depth reads garbage, so the stream header's magic, version and CRC32
    reject it (a 1-in-2^32 chance of a false accept). Every failure is the same
    uniform ``NoHiddenDataError``, so this reveals nothing extra.
    """
    for bits_per_sample in AUTO_DETECT_ORDER:
        try:
            return (
                extract(
                    stego,
                    mode=mode,
                    stego_passphrase=stego_passphrase,
                    bits_per_sample=bits_per_sample,
                ),
                bits_per_sample,
            )
        except NoHiddenDataError:
            continue
    raise NoHiddenDataError("No hidden data found.")


def extract(
    stego: NDArray[np.uint8],
    *,
    mode: EmbeddingMode = "keyed",
    stego_passphrase: str | None = None,
    bits_per_sample: int = 1,
) -> bytes:
    """Extract packet bytes from a grayscale or RGB stego image.

    Args:
        stego: C-order grayscale or RGB image containing an embedded stream.
        mode: Keyed ChaCha20 scatter or sequential mode.
        stego_passphrase: Passphrase used when the data was embedded in keyed mode.
        bits_per_sample: 1 for LSB replacement/matching, 2 for 2-LSB, 0 for STC.

    Returns:
        The exact embedded payload bytes.

    Raises:
        NoHiddenDataError: If the mode/key is wrong or the stream is missing/corrupt.
        ValueError: If the image array or mode is invalid.
    """
    _validate_image(stego)
    if mode not in {"keyed", "sequential"}:
        raise ValueError(f"Unsupported embedding mode: {mode}.")
    if bits_per_sample == 0:
        return _extract_stc(stego, mode, stego_passphrase)
    if bits_per_sample not in (1, 2):
        raise ValueError("Bits per sample must be 1 or 2.")
    samples = stego.reshape(-1)

    if mode == "sequential":
        return _extract_sequential(samples, bits_per_sample)
    if stego_passphrase is None or len(stego_passphrase) < 8:
        raise NoHiddenDataError("No hidden data found.")
    if samples.size < KEYED_SALT_BITS + HEADER_BITS:
        raise NoHiddenDataError("No hidden data found.")

    salt = bits_to_bytes((samples[:KEYED_SALT_BITS] & 1).astype(np.uint8))
    position_key, whitening_key = derive_stego_keys(stego_passphrase, salt)
    scatter = permutation(position_key, samples.size - KEYED_SALT_BITS)
    header_bits = _read_bits(
        samples, KEYED_SALT_BITS + scatter[: HEADER_BITS // bits_per_sample], bits_per_sample
    )
    encoded_header = _xor_bytes(bits_to_bytes(header_bits), whitening_key)
    header = decode_header(encoded_header)
    max_payload = maximum_payload_bytes(samples.size, "keyed", bits_per_sample)
    if header.payload_length > max_payload:
        raise NoHiddenDataError("No hidden data found.")

    total_bits = (HEADER_BYTES + header.payload_length) * 8
    positions = KEYED_SALT_BITS + scatter[: total_bits // bits_per_sample]
    encoded_stream = bits_to_bytes(_read_bits(samples, positions, bits_per_sample))
    stream = _xor_bytes(encoded_stream, whitening_key)
    return stream[HEADER_BYTES:]


def _extract_sequential(samples: NDArray[np.uint8], bits_per_sample: int = 1) -> bytes:
    """Read, validate, and return a raster-order stream."""
    if samples.size * bits_per_sample < HEADER_BITS:
        raise NoHiddenDataError("No hidden data found.")
    header_positions = np.arange(HEADER_BITS // bits_per_sample, dtype=np.int64)
    header_bytes = bits_to_bytes(_read_bits(samples, header_positions, bits_per_sample))
    header = decode_header(header_bytes)
    if header.payload_length > maximum_payload_bytes(samples.size, "sequential", bits_per_sample):
        raise NoHiddenDataError("No hidden data found.")
    total_bits = (HEADER_BYTES + header.payload_length) * 8
    positions = np.arange(total_bits // bits_per_sample, dtype=np.int64)
    stream = bits_to_bytes(_read_bits(samples, positions, bits_per_sample))
    return stream[HEADER_BYTES:]


def _extract_stc(
    stego: NDArray[np.uint8], mode: EmbeddingMode, stego_passphrase: str | None
) -> bytes:
    """Decode the adaptive STC stream, then apply the project's common header checks."""
    samples = stego.reshape(-1)
    if mode == "keyed":
        if stego_passphrase is None or len(stego_passphrase) < 8:
            raise NoHiddenDataError("No hidden data found.")
        if samples.size < KEYED_SALT_BITS + 64 + HEADER_BITS:
            raise NoHiddenDataError("No hidden data found.")
        salt = bits_to_bytes((samples[:KEYED_SALT_BITS] & 1).astype(np.uint8))
        position_key, whitening_key = derive_stego_keys(stego_passphrase, salt)
        positions = KEYED_SALT_BITS + permutation(position_key, samples.size - KEYED_SALT_BITS)
    else:
        if samples.size < 64 + HEADER_BITS:
            raise NoHiddenDataError("No hidden data found.")
        positions = np.arange(samples.size, dtype=np.int64)
        whitening_key = b""

    try:
        encoded = extract_adaptive(stego, positions)
        stream = _xor_bytes(encoded, whitening_key) if whitening_key else encoded
        if len(stream) < HEADER_BYTES:
            raise NoHiddenDataError("No hidden data found.")
        header = decode_header(stream[:HEADER_BYTES])
        maximum = maximum_payload_bytes(samples.size, mode, method="suniward")
        if header.payload_length > maximum or len(stream) < HEADER_BYTES + header.payload_length:
            raise NoHiddenDataError("No hidden data found.")
        return stream[HEADER_BYTES : HEADER_BYTES + header.payload_length]
    except Exception as exc:
        raise NoHiddenDataError("No hidden data found.") from exc


def _read_bits(
    samples: NDArray[np.uint8], positions: NDArray[np.int64], bits_per_sample: int = 1
) -> NDArray[np.uint8]:
    """Read the embedded bits at the requested flattened sample positions."""
    if positions.size > samples.size or (
        positions.size > 0 and int(np.max(positions)) >= samples.size
    ):
        raise NoHiddenDataError("No hidden data found.")
    return lsb_replace.read_bits(samples, positions, bits_per_sample)


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """Apply the keyed ChaCha20 whitening stream."""
    pad = chacha20_keystream(key, len(data))
    return bytes(left ^ right for left, right in zip(data, pad, strict=True))
