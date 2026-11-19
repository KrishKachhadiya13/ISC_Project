"""2-LSB embedding: round trips, capacity, distortion, and bit-depth auto-detection."""

import numpy as np
import pytest

from app.core.stego import lsb_replace
from app.core.stego.embed import BITS_PER_SAMPLE, embed, maximum_payload_bytes
from app.core.stego.exceptions import CapacityExceededError, NoHiddenDataError
from app.core.stego.extract import extract, extract_auto
from app.core.stego.metrics import calculate_metrics

PASSPHRASE = "a long enough passphrase"


def _cover(shape: tuple[int, ...] = (96, 96), seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, shape, dtype=np.uint8)


def _payload(size: int, seed: int = 1) -> bytes:
    return bytes(np.random.default_rng(seed).integers(0, 256, size, dtype=np.uint8))


@pytest.mark.parametrize("shape", [(96, 96), (64, 64, 3)])
@pytest.mark.parametrize("mode", ["keyed", "sequential"])
def test_2lsb_round_trip(shape: tuple[int, ...], mode: str) -> None:
    """The payload comes back exactly, with and without the keyed scatter."""
    cover, payload = _cover(shape), _payload(700)
    stego = embed(cover, payload, method="lsb2_replace", mode=mode, stego_passphrase=PASSPHRASE)  # type: ignore[arg-type]
    assert extract(stego, mode=mode, stego_passphrase=PASSPHRASE, bits_per_sample=2) == payload  # type: ignore[arg-type]


def test_2lsb_changes_only_the_two_low_bits_and_never_leaves_the_range() -> None:
    """Upper six bits are untouched, so every change is at most 3."""
    cover = _cover(seed=3)
    stego = embed(cover, _payload(800), method="lsb2_replace", stego_passphrase=PASSPHRASE)
    assert np.array_equal(cover >> 2, stego >> 2)
    assert int(np.abs(stego.astype(int) - cover.astype(int)).max()) <= 3


def test_2lsb_doubles_capacity() -> None:
    """For the same cover, 2-LSB fits about twice the bits of 1-LSB."""
    samples = 96 * 96
    one = maximum_payload_bytes(samples, "keyed", 1)
    two = maximum_payload_bytes(samples, "keyed", 2)
    assert 1.9 < (two + 13) / (one + 13) < 2.1
    cover = _cover()
    embed(
        cover, _payload(two), method="lsb2_replace", stego_passphrase=PASSPHRASE
    )  # exactly at capacity
    with pytest.raises(CapacityExceededError):
        embed(cover, _payload(two + 1), method="lsb2_replace", stego_passphrase=PASSPHRASE)
    with pytest.raises(CapacityExceededError):  # fits 2-LSB but not 1-LSB
        embed(cover, _payload(one + 50), method="lsb_replace", stego_passphrase=PASSPHRASE)


def test_2lsb_distortion_matches_theory() -> None:
    """Random 2-bit symbols replacing random 2-bit values give MSE about 1.25 * bpp.

    Each modified sample changes by the difference of two independent uniform values
    on {0..3}, whose expected square is 2.5; only half as many samples are touched as
    with 1-LSB for the same number of embedded bits, so MSE = 2.5 * (bpp / 2).
    """
    cover = _cover((128, 128), seed=5)
    payload = _payload(1000)
    stego = embed(cover, payload, method="lsb2_replace", stego_passphrase=PASSPHRASE)
    bits = (len(payload) + 13) * 8 + 128
    metrics = calculate_metrics(cover, stego, bits)
    expected = 1.25 * (len(payload) + 13) * 8 / cover.size
    assert metrics.mse == pytest.approx(expected, rel=0.2)


def test_auto_detect_finds_the_right_depth_and_reports_it() -> None:
    """Whichever depth was used, extract_auto returns it."""
    cover, payload = _cover(seed=7), _payload(300, seed=2)
    for method in ("lsb_replace", "lsb_match", "lsb2_replace"):
        stego = embed(cover, payload, method=method, stego_passphrase=PASSPHRASE)  # type: ignore[arg-type]
        data, depth = extract_auto(stego, stego_passphrase=PASSPHRASE)
        assert data == payload and depth == BITS_PER_SAMPLE[method]


def test_wrong_depth_is_indistinguishable_from_no_data() -> None:
    """Forcing the wrong depth, a wrong key, or a clean image all raise the same error."""
    cover, payload = _cover(seed=9), _payload(200)
    stego = embed(cover, payload, method="lsb2_replace", stego_passphrase=PASSPHRASE)
    for kwargs in (
        {"stego_passphrase": PASSPHRASE, "bits_per_sample": 1},
        {"stego_passphrase": "another long passphrase", "bits_per_sample": 2},
    ):
        with pytest.raises(NoHiddenDataError):
            extract(stego, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(NoHiddenDataError):
        extract_auto(cover, stego_passphrase=PASSPHRASE)
    with pytest.raises(NoHiddenDataError):
        extract_auto(stego, stego_passphrase="another long passphrase")


def test_keyed_2lsb_spreads_changes_over_the_whole_image() -> None:
    """Keyed scatter still spreads the changes; sequential confines them to the top rows."""
    cover, payload = _cover((128, 128), seed=11), _payload(300)
    keyed = embed(cover, payload, method="lsb2_replace", stego_passphrase=PASSPHRASE)
    sequential = embed(cover, payload, method="lsb2_replace", mode="sequential")
    keyed_rows = (cover != keyed).sum(axis=1)
    sequential_rows = (cover != sequential).sum(axis=1)
    assert keyed_rows.min() > 0
    assert sequential_rows[64:].sum() == 0


def test_lsb_replace_helpers_validate_arguments() -> None:
    """The shared bit writer rejects impossible inputs."""
    samples = np.zeros(8, dtype=np.uint8)
    positions = np.arange(4, dtype=np.int64)
    with pytest.raises(ValueError, match="1 or 2"):
        lsb_replace.embed_bits(samples, positions, np.zeros(4, np.uint8), bits_per_sample=3)
    with pytest.raises(ValueError, match="counts must match"):
        lsb_replace.embed_bits(samples, positions, np.zeros(4, np.uint8), bits_per_sample=2)
    with pytest.raises(ValueError, match="1 or 2"):
        lsb_replace.read_bits(samples, positions, bits_per_sample=0)
    bits = np.array([1, 0, 0, 1, 1, 1, 0, 0], dtype=np.uint8)
    written = lsb_replace.embed_bits(samples, positions, bits, bits_per_sample=2)
    assert written[:4].tolist() == [2, 1, 3, 0]  # symbols 10, 01, 11, 00
    assert lsb_replace.read_bits(written, positions, 2).tolist() == bits.tolist()
