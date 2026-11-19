"""Message-carrying S-UNIWARD and HILL embedding through syndrome-trellis codes."""

from __future__ import annotations

import struct
import threading
from typing import Any, Literal, cast

import numpy as np
from numpy.typing import NDArray

from app.core.stego.exceptions import StcUnavailableError
from app.core.stego.simulate import hill_cost, suniward_cost

AdaptiveMethod = Literal["suniward", "hill"]
_STC_LOCK = threading.Lock()
_STC_LENGTH_SAMPLES = 64
_MAX_MESSAGE_BITS = (1 << 32) - 1


def _stc() -> Any:
    """Import pySTC on first use so the rest of the app runs without its compiled extension."""
    try:
        from pystc import pystc as wrapper
    except ImportError as exc:
        raise StcUnavailableError(
            "S-UNIWARD and HILL need the optional pystcstego package, which is not installed."
        ) from exc
    return wrapper


def adaptive_costs(cover: NDArray[np.uint8], method: AdaptiveMethod) -> NDArray[np.float64]:
    """Calculate the chosen scheme's additive cost for every grayscale or RGB sample."""
    cost_function = suniward_cost if method == "suniward" else hill_cost
    if cover.ndim == 2:
        return cost_function(cover).reshape(-1)
    channel_costs = [cost_function(cover[:, :, channel]) for channel in range(3)]
    return np.stack(channel_costs, axis=-1).reshape(-1)


def embed_adaptive(
    cover: NDArray[np.uint8],
    payload: bytes,
    method: AdaptiveMethod,
    positions: NDArray[np.int64],
) -> NDArray[np.uint8]:
    """Embed bytes using STC to minimize the selected cover's additive costs.

    The caller supplies sample positions in the order shared with the receiver. In keyed mode
    those positions come from the project's ChaCha20 permutation; no extra RNG is needed.
    """
    if not payload:
        raise ValueError("Adaptive embedding requires a non-empty framed payload.")
    if len(payload) * 8 > _MAX_MESSAGE_BITS:
        raise ValueError("Adaptive payload is too long for the STC length field.")
    if positions.size < _STC_LENGTH_SAMPLES + len(payload) * 8:
        raise ValueError("Adaptive payload exceeds STC capacity.")

    flat_cover = cover.reshape(-1)
    cover_values = flat_cover[positions]
    costs = adaptive_costs(cover, method)[positions].astype(np.float32)
    length_bits = _bytes_to_lsb_first_bits(struct.pack("!I", len(payload) * 8))
    message_bits = _bytes_to_lsb_first_bits(payload)
    # Split the fixed length prelude from the message exactly as the pinned wrapper does.
    # Calling its lower-level encoder avoids its extra Python-random sample shuffle.
    with _STC_LOCK:
        length_stego = _stc()._hide_stc(
            cover_values[:_STC_LENGTH_SAMPLES],
            costs[:_STC_LENGTH_SAMPLES],
            costs[:_STC_LENGTH_SAMPLES],
            length_bits,
        )
        message_stego = _stc()._hide_stc(
            cover_values[_STC_LENGTH_SAMPLES:],
            costs[_STC_LENGTH_SAMPLES:],
            costs[_STC_LENGTH_SAMPLES:],
            message_bits,
        )
    stego_values = np.concatenate((length_stego, message_stego))
    result = flat_cover.copy()
    result[positions] = np.asarray(stego_values, dtype=np.uint8).reshape(-1)
    return result.reshape(cover.shape)


def extract_adaptive(stego: NDArray[np.uint8], positions: NDArray[np.int64]) -> bytes:
    """Recover framed bytes from an STC image without needing its cover or cost map."""
    values = stego.reshape(-1)[positions].astype(np.int32)
    if values.size <= _STC_LENGTH_SAMPLES:
        raise ValueError("Image is too small for an STC length header.")

    with _STC_LOCK:
        length_bytes = _stc()._unhide_stc(values[:_STC_LENGTH_SAMPLES], 32)
        (message_bits,) = struct.unpack("!I", length_bytes)
        if message_bits == 0 or message_bits > values.size - _STC_LENGTH_SAMPLES:
            raise ValueError("Invalid STC message length.")
        return cast(
            bytes,
            _stc()._unhide_stc(values[_STC_LENGTH_SAMPLES:], message_bits),
        )


def _bytes_to_lsb_first_bits(data: bytes) -> NDArray[np.uint8]:
    """Expand bytes in the least-significant-bit-first order expected by pySTC."""
    if not data:
        return np.empty(0, dtype=np.uint8)
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8), bitorder="little")
