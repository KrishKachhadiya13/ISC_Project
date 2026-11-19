"""Real adaptive embedding round trips through syndrome-trellis coding."""

import numpy as np
import pytest

from app.core.stego import adaptive
from app.core.stego.embed import embed, maximum_payload_bytes
from app.core.stego.exceptions import (
    CapacityExceededError,
    NoHiddenDataError,
    StcUnavailableError,
)
from app.core.stego.extract import extract, extract_auto

PASSPHRASE = "adaptive coding passphrase"


def stc_installed() -> bool:
    """True when the compiled pySTC extension can be imported (it needs a C++ compiler to build)."""
    try:
        from pystc import pystc  # noqa: F401
    except ImportError:
        return False
    return True


needs_stc = pytest.mark.skipif(not stc_installed(), reason="pystcstego is not installed")


def _cover(shape: tuple[int, ...] = (96, 96)) -> np.ndarray:
    """Build deterministic texture with valid 8-bit samples."""
    return np.random.default_rng(817).integers(0, 256, shape, dtype=np.uint8)


@needs_stc
@pytest.mark.parametrize("method", ["suniward", "hill"])
@pytest.mark.parametrize("mode", ["keyed", "sequential"])
def test_adaptive_stc_round_trip(method: str, mode: str) -> None:
    """Both cost maps carry exact payload bytes in keyed and public placement modes."""
    cover = _cover()
    payload = bytes(range(64))
    stego = embed(
        cover,
        payload,
        method=method,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        stego_passphrase=PASSPHRASE,
    )
    assert extract(stego, mode=mode, stego_passphrase=PASSPHRASE, bits_per_sample=0) == payload  # type: ignore[arg-type]
    assert extract_auto(stego, mode=mode, stego_passphrase=PASSPHRASE) == (payload, 0)  # type: ignore[arg-type]
    assert np.max(np.abs(stego.astype(np.int16) - cover.astype(np.int16))) <= 1


@needs_stc
def test_adaptive_stc_supports_rgb_and_rejects_wrong_key() -> None:
    """Channel-interleaved positions stay aligned, and a wrong scatter key fails closed."""
    cover = _cover((64, 64, 3))
    stego = embed(cover, b"rgb payload", method="hill", stego_passphrase=PASSPHRASE)
    assert extract(stego, stego_passphrase=PASSPHRASE, bits_per_sample=0) == b"rgb payload"
    with pytest.raises(NoHiddenDataError):
        extract(stego, stego_passphrase="wrong adaptive passphrase", bits_per_sample=0)


def test_adaptive_capacity_accounts_for_stc_and_stream_headers() -> None:
    """The UI/API capacity excludes the keyed salt, STC framing and common stream header."""
    samples = 96 * 96
    expected = (samples - 128 - 64 - 104) // 8
    assert maximum_payload_bytes(samples, "keyed", method="hill") == expected
    with pytest.raises(CapacityExceededError):
        embed(_cover((8, 8)), b"too large", method="suniward", stego_passphrase=PASSPHRASE)


def test_missing_stc_package_gives_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without pystcstego, embedding says so; the rest of the app is unaffected."""

    def unavailable() -> None:
        raise StcUnavailableError("not installed")

    monkeypatch.setattr(adaptive, "_stc", unavailable)
    with pytest.raises(StcUnavailableError):
        embed(_cover(), b"payload", method="hill", stego_passphrase=PASSPHRASE)
    # Receiving never crashes: a failed STC decode reads as "no hidden data".
    plain = embed(_cover(), b"payload", method="lsb_replace", stego_passphrase=PASSPHRASE)
    with pytest.raises(NoHiddenDataError):
        extract(plain, stego_passphrase=PASSPHRASE, bits_per_sample=0)
