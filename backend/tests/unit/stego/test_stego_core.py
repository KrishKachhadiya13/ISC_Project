"""Tests for Phase 2 image I/O, embedding, extraction, and analysis helpers."""

from io import BytesIO
from time import perf_counter

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image

from app.core.analysis.bitplane import extract_bitplane
from app.core.analysis.diffmap import amplified_difference
from app.core.stego import lsb_match, lsb_replace
from app.core.stego.bitops import bits_to_bytes, bytes_to_bits
from app.core.stego.embed import embed, maximum_payload_bytes
from app.core.stego.exceptions import (
    CapacityExceededError,
    InvalidImageError,
    NoHiddenDataError,
    UnsupportedImageError,
)
from app.core.stego.extract import extract
from app.core.stego.header import HEADER_BYTES, decode_header, encode_header
from app.core.stego.image_io import load_image, save_png
from app.core.stego.keystream import chacha20_keystream
from app.core.stego.metrics import calculate_metrics
from app.core.stego.scatter import derive_stego_keys, permutation


@pytest.mark.parametrize("payload", [b"", b"\x00", b"\xff\x01", bytes(range(128))])
def test_bit_conversion_round_trip(payload: bytes) -> None:
    """Byte and bit conversions use the specified MSB-first order."""
    bits = bytes_to_bits(payload)
    assert bits_to_bytes(bits) == payload
    if payload:
        assert bits[:8].tolist() == [int(bit) for bit in f"{payload[0]:08b}"]


def test_bit_conversion_rejects_invalid_vectors() -> None:
    """Invalid bit vector shape, length, and values are rejected."""
    with pytest.raises(ValueError, match="one-dimensional"):
        bits_to_bytes(np.zeros((1, 8), dtype=np.uint8))
    with pytest.raises(ValueError, match="divisible by 8"):
        bits_to_bytes(np.zeros(7, dtype=np.uint8))
    with pytest.raises(ValueError, match="only zero and one"):
        bits_to_bytes(np.array([2] * 8, dtype=np.uint8))


def test_chacha20_is_repeatable_and_validates_parameters() -> None:
    """Keystream bytes are deterministic and malformed parameters fail early."""
    key = bytes(range(32))
    assert chacha20_keystream(key, 64) == chacha20_keystream(key, 64)
    assert chacha20_keystream(key, 0) == b""
    with pytest.raises(ValueError, match="key must"):
        chacha20_keystream(b"short", 1)
    with pytest.raises(ValueError, match="nonce must"):
        chacha20_keystream(key, 1, b"short")
    with pytest.raises(ValueError, match="non-negative"):
        chacha20_keystream(key, -1)


def test_scatter_is_valid_deterministic_and_key_dependent() -> None:
    """Same key reproduces a valid permutation and another key changes it."""
    first = permutation(bytes(32), 1024)
    assert np.array_equal(first, permutation(bytes(32), 1024))
    assert not np.array_equal(first, permutation(bytes([1]) * 32, 1024))
    assert np.array_equal(np.sort(first), np.arange(1024))
    assert permutation(bytes(32), 0).size == 0
    with pytest.raises(ValueError, match="exactly 32"):
        permutation(b"bad", 10)
    with pytest.raises(ValueError, match="between 0"):
        permutation(bytes(32), -1)


def test_header_format_and_corruption_checks() -> None:
    """Header is 13 bytes and invalid magic, version, CRC, or length fails."""
    header = encode_header(257)
    assert len(header) == HEADER_BYTES
    assert decode_header(header).payload_length == 257
    with pytest.raises(ValueError, match="unsigned 32-bit"):
        encode_header(1 << 32)
    for index in (0, 4, 9):
        corrupted = bytearray(header)
        corrupted[index] ^= 1
        with pytest.raises(NoHiddenDataError):
            decode_header(bytes(corrupted))
    with pytest.raises(NoHiddenDataError):
        decode_header(b"")


def test_lsb_replacement_and_matching_bounds() -> None:
    """Both embedding operations write bits correctly and matching changes ±1."""
    source = np.array([0, 1, 254, 255, 40, 41], dtype=np.uint8)
    positions = np.arange(source.size, dtype=np.int64)
    bits = np.array([1, 0, 1, 0, 1, 0], dtype=np.uint8)
    replaced = lsb_replace.embed_bits(source, positions, bits)
    assert np.array_equal(replaced & 1, bits)

    matched = lsb_match.embed_bits(source, positions, bits)
    assert np.array_equal(matched & 1, bits)
    changes = np.abs(matched.astype(np.int16) - source.astype(np.int16))
    assert np.all(np.isin(changes, (0, 1)))
    assert matched.min() >= 0 and matched.max() <= 255
    with pytest.raises(ValueError, match="counts must match"):
        lsb_match.embed_bits(source, positions[:-1], bits)
    with pytest.raises(ValueError, match="counts must match"):
        lsb_replace.embed_bits(source, positions[:-1], bits)
    with pytest.raises(ValueError, match="only zero and one"):
        lsb_replace.embed_bits(source, positions, np.full(6, 2, dtype=np.uint8))


def test_sequential_gray_and_rgb_round_trips_both_methods() -> None:
    """Sequential extraction recovers exact bytes for each supported shape/method."""
    payload = bytes(range(40))
    for shape in ((80, 80), (80, 80, 3)):
        cover = np.random.default_rng(42).integers(0, 256, shape, dtype=np.uint8)
        for method in ("lsb_replace", "lsb_match"):
            stego = embed(cover, payload, mode="sequential", method=method)
            assert np.array_equal(cover, stego) is False
            assert extract(stego, mode="sequential") == payload
            assert np.array_equal(cover, stego) is False


@settings(max_examples=20, deadline=None)
@given(st.binary(min_size=0, max_size=200))
def test_sequential_round_trip_random_payloads(payload: bytes) -> None:
    """Arbitrary byte payloads fit and round-trip exactly in sequential mode."""
    cover = np.zeros((32, 32), dtype=np.uint8)
    assert extract(embed(cover, payload, mode="sequential"), mode="sequential") == payload


def test_keyed_gray_rgb_round_trip_wrong_key_and_mode() -> None:
    """Keyed mode round-trips and maps wrong passphrases/modes to no-data errors."""
    payload = b"keyed-packet"
    for shape in ((80, 80), (80, 80, 3)):
        cover = np.random.default_rng(1).integers(0, 256, shape, dtype=np.uint8)
        for method in ("lsb_replace", "lsb_match"):
            stego = embed(cover, payload, method=method, stego_passphrase="correct horse")
            assert extract(stego, stego_passphrase="correct horse") == payload
            with pytest.raises(NoHiddenDataError):
                extract(stego, stego_passphrase="wrong password")
            with pytest.raises(NoHiddenDataError):
                extract(stego, mode="sequential")
    with pytest.raises(ValueError, match="at least 8"):
        embed(np.zeros((80, 80), dtype=np.uint8), payload, stego_passphrase="short")


def test_capacity_exact_and_one_byte_over() -> None:
    """Payload capacity includes the 13-byte header and keyed salt reservation."""
    for mode, shape in (("sequential", (40, 40)), ("keyed", (40, 40))):
        maximum = maximum_payload_bytes(40 * 40, mode)  # type: ignore[arg-type]
        cover = np.zeros(shape, dtype=np.uint8)
        kwargs = {"mode": mode}
        if mode == "keyed":
            kwargs["stego_passphrase"] = "capacity test"
        stego = embed(cover, bytes(maximum), **kwargs)  # type: ignore[arg-type]
        assert len(extract(stego, **kwargs)) == maximum  # type: ignore[arg-type]
        with pytest.raises(CapacityExceededError) as error:
            embed(cover, bytes(maximum + 1), **kwargs)  # type: ignore[arg-type]
        assert error.value.maximum_payload_bytes == maximum


def test_header_only_payload_requires_full_header_capacity() -> None:
    """Even an empty payload needs room for its fixed stream header."""
    with pytest.raises(CapacityExceededError):
        embed(np.zeros((8, 8), dtype=np.uint8), b"", mode="sequential")
    with pytest.raises(CapacityExceededError):
        embed(np.zeros((15, 15), dtype=np.uint8), b"", stego_passphrase="empty payload")


def test_embed_extract_validate_inputs_and_headerless_image() -> None:
    """Unsupported shapes, methods, modes, and missing headers are rejected."""
    image = np.zeros((32, 32), dtype=np.uint8)
    with pytest.raises(ValueError, match="uint8"):
        embed(image.astype(np.float32), b"", mode="sequential")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported embedding method"):
        embed(image, b"", method="other", mode="sequential")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported embedding mode"):
        embed(image, b"", mode="other")  # type: ignore[arg-type]
    with pytest.raises(NoHiddenDataError):
        extract(image, mode="sequential")
    with pytest.raises(ValueError, match="Unsupported embedding mode"):
        extract(image, mode="other")  # type: ignore[arg-type]


def test_png_round_trip_and_image_format_guards() -> None:
    """PNG save/load preserves pixels while JPEG embedding and malformed bytes fail."""
    image = np.random.default_rng(4).integers(0, 256, (32, 32, 3), dtype=np.uint8)
    stego = embed(image, b"png payload", mode="sequential")
    decoded, warnings = load_image(save_png(stego), for_embedding=True)
    assert not warnings
    assert np.array_equal(decoded, stego)
    assert extract(decoded, mode="sequential") == b"png payload"

    jpeg_buffer = BytesIO()
    Image.fromarray(stego).save(jpeg_buffer, format="JPEG", quality=95)
    with pytest.raises(UnsupportedImageError, match="JPEG is lossy"):
        load_image(jpeg_buffer.getvalue(), for_embedding=True)
    jpeg_decoded, _ = load_image(jpeg_buffer.getvalue())
    with pytest.raises(NoHiddenDataError):
        extract(jpeg_decoded, mode="sequential")
    with pytest.raises(InvalidImageError):
        load_image(b"not an image")
    with pytest.raises(InvalidImageError):
        load_image(b"")


def test_image_loader_rejects_16_bit_and_unsupported_modes() -> None:
    """Non-8-bit and unsupported Pillow modes are not silently converted."""
    for mode, image_format in (("I;16", "PNG"), ("F", "TIFF"), ("1", "PNG")):
        source = Image.new(mode, (8, 8))
        output = BytesIO()
        source.save(output, format=image_format)
        with pytest.raises(UnsupportedImageError):
            load_image(output.getvalue())


def test_png_metadata_is_not_carried_forward() -> None:
    """Saving a pixel array produces a PNG without inherited EXIF metadata."""
    image = np.zeros((8, 8), dtype=np.uint8)
    encoded = save_png(image)
    with Image.open(BytesIO(encoded)) as reloaded:
        assert not reloaded.getexif()


@pytest.mark.parametrize(
    ("mode", "warning"),
    [("RGBA", "alpha channel discarded"), ("P", "palette image converted to RGB")],
)
def test_image_loader_converts_supported_modes(mode: str, warning: str) -> None:
    """Alpha and palette modes are converted to RGB with a visible warning."""
    source = Image.new(mode, (8, 8))
    output = BytesIO()
    source.save(output, format="PNG")
    array, warnings = load_image(output.getvalue())
    assert array.shape == (8, 8, 3)
    assert warning in warnings


def test_image_io_validation() -> None:
    """Image serialization rejects invalid shape and sample arrays."""
    with pytest.raises(ValueError, match="uint8"):
        save_png(np.zeros((8, 8), dtype=np.float32))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="shape"):
        save_png(np.zeros((8, 8, 4), dtype=np.uint8))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        save_png(np.zeros((0, 8), dtype=np.uint8))


def test_argon_and_hkdf_key_lengths() -> None:
    """The passphrase and salt derive distinct fixed-size position and whitening keys."""
    key_pos, key_wh = derive_stego_keys("test passphrase", bytes(16))
    assert len(key_pos) == len(key_wh) == 32
    assert key_pos != key_wh
    with pytest.raises(ValueError, match="16 bytes"):
        derive_stego_keys("test passphrase", b"bad")


def test_quality_metrics_and_maps() -> None:
    """Metrics report image quality and map expected pixel differences."""
    cover = np.full((16, 16), 100, dtype=np.uint8)
    stego = cover.copy()
    stego[0, 0] += 1
    metrics = calculate_metrics(cover, stego, 8)
    assert metrics.mse == pytest.approx(1 / 256)
    assert metrics.psnr == pytest.approx(10 * np.log10(255**2 * 256))
    assert 0 < metrics.ssim < 1
    assert metrics.fraction_changed == pytest.approx(1 / 256)
    assert metrics.embedded_bits == 8
    assert metrics.bpp == pytest.approx(8 / 16**2)
    assert metrics.difference_map[0, 0] == 50
    assert np.all(metrics.difference_map[1:, :] == 0)
    assert amplified_difference(cover, stego, 300)[0, 0] == 255
    assert extract_bitplane(np.array([[0, 255]], dtype=np.uint8), 0).tolist() == [[0, 255]]
    with pytest.raises(ValueError, match="between 0 and 7"):
        extract_bitplane(cover, 8)
    with pytest.raises(ValueError, match="uint8"):
        extract_bitplane(cover.astype(np.float32))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative"):
        amplified_difference(cover, stego, -1)


def test_replacement_mse_matches_random_payload_sanity() -> None:
    """Random LSB replacement changes about half of the addressed samples."""
    rng = np.random.default_rng(38)
    cover = rng.integers(0, 256, (256, 256), dtype=np.uint8)
    payload = rng.bytes(8000)
    stego = embed(cover, payload, mode="sequential")
    embedded_bits = (HEADER_BYTES + len(payload)) * 8
    metrics = calculate_metrics(cover, stego, embedded_bits)
    expected_mse = 0.5 * embedded_bits / cover.size
    assert metrics.mse == pytest.approx(expected_mse, rel=0.08)


def test_metrics_validation_and_rgb() -> None:
    """Metrics validate dimensions and support the documented RGB channel axis."""
    cover = np.zeros((8, 8, 3), dtype=np.uint8)
    assert calculate_metrics(cover, cover.copy(), 0).psnr == float("inf")
    with pytest.raises(ValueError, match="at least 7x7"):
        calculate_metrics(np.zeros((6, 8), dtype=np.uint8), np.zeros((6, 8), dtype=np.uint8), 0)
    with pytest.raises(ValueError, match="non-negative"):
        calculate_metrics(cover, cover.copy(), -1)
    with pytest.raises(ValueError, match="matching"):
        amplified_difference(cover, np.zeros((8, 8), dtype=np.uint8))
    with pytest.raises(ValueError, match="uint8"):
        calculate_metrics(cover.astype(np.float32), cover, 0)  # type: ignore[arg-type]


@pytest.mark.slow
def test_512_rgb_embed_and_extract_complete_under_one_second() -> None:
    """Embedding and extraction meet the Phase 2 512x512 RGB performance target."""
    cover = np.zeros((512, 512, 3), dtype=np.uint8)
    started = perf_counter()
    stego = embed(cover, b"performance", stego_passphrase="performance passphrase")
    assert extract(stego, stego_passphrase="performance passphrase") == b"performance"
    assert perf_counter() - started < 1.0


def test_keyed_change_positions_are_spread_across_rows() -> None:
    """A keyed stream distributes changes across rows instead of a top-row prefix."""
    cover = np.zeros((96, 96), dtype=np.uint8)
    stego = embed(cover, bytes(300), stego_passphrase="spread sample")
    changed_rows = np.flatnonzero(np.any(cover != stego, axis=1))
    assert changed_rows.size > 60


def test_sequential_changes_are_confined_to_top_rows_for_small_payload() -> None:
    """Raster-order embedding modifies only the top rows for a small message."""
    cover = np.zeros((128, 128), dtype=np.uint8)
    stego = embed(cover, b"small", mode="sequential")
    changed_rows = np.flatnonzero(np.any(cover != stego, axis=1))
    assert changed_rows.max() < 2
