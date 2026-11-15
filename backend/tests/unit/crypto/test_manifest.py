"""Tests for signed integrity manifest creation and canonical verification."""

import copy

import numpy as np

from app.core.crypto.keys import generate_keypair
from app.core.crypto.manifest import (
    canonical_json_encode,
    compute_pixel_sha256,
    create_manifest,
    verify_manifest,
)


def test_canonical_json_stability() -> None:
    """Canonical JSON encoding produces identical bytes regardless of dictionary key order."""
    dict_a = {"b": 2, "a": 1, "nested": {"z": 26, "y": 25}}
    dict_b = {"a": 1, "b": 2, "nested": {"y": 25, "z": 26}}

    assert canonical_json_encode(dict_a) == canonical_json_encode(dict_b)


def test_manifest_round_trip() -> None:
    """Valid manifest verifies completely."""
    priv, pub = generate_keypair()
    stego_array = np.random.randint(0, 256, (128, 128, 3), dtype=np.uint8)
    cover_array = stego_array.copy()
    stego_file_bytes = b"fake-png-file-content"

    manifest = create_manifest(
        stego_array=stego_array,
        stego_file_bytes=stego_file_bytes,
        method="lsb_replace",
        mode="keyed",
        payload_bytes=256,
        payload_bpp=0.05,
        private_key=priv,
        cover_array=cover_array,
    )

    valid, details = verify_manifest(manifest, stego_array, pub, stego_file_bytes)
    assert valid is True
    assert details["signature_valid"] is True
    assert details["pixel_hash_valid"] is True
    assert details["fingerprint_valid"] is True
    assert details["file_hash_valid"] is True


def test_pixel_tampering_fails_verification() -> None:
    """Flipping a single pixel anywhere in the stego image fails verification."""
    priv, pub = generate_keypair()
    stego_array = np.zeros((64, 64), dtype=np.uint8)
    stego_file_bytes = b"png-bytes"

    manifest = create_manifest(
        stego_array=stego_array,
        stego_file_bytes=stego_file_bytes,
        method="lsb_replace",
        mode="keyed",
        payload_bytes=10,
        payload_bpp=0.01,
        private_key=priv,
    )

    # Tamper a single pixel
    tampered_array = stego_array.copy()
    tampered_array[32, 32] = 1

    valid, details = verify_manifest(manifest, tampered_array, pub, stego_file_bytes)
    assert valid is False
    assert details["pixel_hash_valid"] is False
    assert details["signature_valid"] is True  # Manifest signature itself wasn't touched


def test_manifest_field_tampering_invalidates_signature() -> None:
    """Modifying any field in the manifest document causes signature check to fail."""
    priv, pub = generate_keypair()
    stego_array = np.full((32, 32), 128, dtype=np.uint8)
    stego_file_bytes = b"file-bytes"

    manifest = create_manifest(
        stego_array=stego_array,
        stego_file_bytes=stego_file_bytes,
        method="lsb_replace",
        mode="keyed",
        payload_bytes=50,
        payload_bpp=0.05,
        private_key=priv,
    )

    # Test tampering various manifest fields
    fields_to_tamper = ["method", "mode", "payload_bytes", "payload_bpp", "version"]
    for field in fields_to_tamper:
        tampered_manifest = copy.deepcopy(manifest)
        if isinstance(tampered_manifest[field], int):
            tampered_manifest[field] += 1
        elif isinstance(tampered_manifest[field], float):
            tampered_manifest[field] += 0.1
        else:
            tampered_manifest[field] = "tampered_value"

        valid, details = verify_manifest(tampered_manifest, stego_array, pub, stego_file_bytes)
        assert valid is False
        assert details["signature_valid"] is False


def test_pixel_sha256_format_and_properties() -> None:
    """Pixel hash binds dimensions, channels, and content."""
    arr1 = np.zeros((10, 20), dtype=np.uint8)
    arr2 = np.zeros((20, 10), dtype=np.uint8)  # Same total pixels, different dimensions
    arr3 = np.zeros((10, 20, 1), dtype=np.uint8)

    h1 = compute_pixel_sha256(arr1)
    h2 = compute_pixel_sha256(arr2)
    h3 = compute_pixel_sha256(arr3)

    assert h1 != h2
    assert len(h1) == 64
    assert h1 == h3  # 2D (10, 20) and 3D (10, 20, 1) both represent H=10, W=20, C=1
