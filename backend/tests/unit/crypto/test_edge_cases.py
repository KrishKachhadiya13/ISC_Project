"""Targeted tests for crypto edge cases, parameter validations, and error paths."""

import numpy as np
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.crypto import aead, keys, manifest, packet, signing
from app.core.crypto.exceptions import (
    CryptoError,
    DecryptionFailedError,
    InvalidPacketError,
)


def test_aead_parameter_length_errors() -> None:
    """Validate AEAD length guards."""
    valid_key = bytes(32)
    valid_nonce = bytes(12)

    with pytest.raises(CryptoError, match="key must be exactly 32 bytes"):
        aead.decrypt(b"short", valid_nonce, bytes(20))

    with pytest.raises(CryptoError, match="nonce must be exactly 12 bytes"):
        aead.decrypt(valid_key, b"short", bytes(20))


def test_keys_non_ed25519_pem_rejection() -> None:
    """Ensure RSA keys cannot be loaded as Ed25519 keys."""
    rsa_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_priv_pem = rsa_priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(b"Password123"),
    ).decode("utf-8")

    with pytest.raises(CryptoError, match="not an Ed25519 private key"):
        keys.load_private_key_pem(rsa_priv_pem, "Password123")

    rsa_pub = rsa_priv.public_key()
    rsa_pub_pem = rsa_pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    with pytest.raises(CryptoError, match="not an Ed25519 public key"):
        keys.load_public_key_pem(rsa_pub_pem)


def test_manifest_array_shape_validation() -> None:
    """Pixel hash and manifest require 2D or 3D uint8 arrays."""
    priv, pub = keys.generate_keypair()

    with pytest.raises(ValueError, match="must be uint8"):
        manifest.compute_pixel_sha256(np.zeros((10, 10), dtype=np.float32))

    with pytest.raises(ValueError, match="Unsupported array dimensions"):
        manifest.compute_pixel_sha256(np.zeros((10, 10, 3, 2), dtype=np.uint8))

    with pytest.raises(ValueError, match="Invalid array shape"):
        manifest.create_manifest(
            stego_array=np.zeros((10, 10, 3, 2), dtype=np.uint8),
            stego_file_bytes=b"png",
            method="lsb_replace",
            mode="keyed",
            payload_bytes=10,
            payload_bpp=0.1,
            private_key=priv,
        )

    # Missing signature in manifest dict
    bad_manifest = {"version": 1}
    valid, details = manifest.verify_manifest(bad_manifest, np.zeros((10, 10), dtype=np.uint8), pub)
    assert valid is False
    assert "Missing signature" in details.get("error", "")

    # Malformed base64 signature
    bad_manifest2 = {"version": 1, "signature": "not-valid-base64!!!"}
    valid2, details2 = manifest.verify_manifest(
        bad_manifest2, np.zeros((10, 10), dtype=np.uint8), pub
    )
    assert valid2 is False
    assert "Invalid base64" in details2.get("error", "")


def test_packet_inner_framing_validations() -> None:
    """Inner plaintext format boundary validations."""
    with pytest.raises(CryptoError, match="Filename exceeds maximum"):
        packet.format_inner_plaintext(b"data", is_file=True, filename="a" * 70000)

    with pytest.raises(InvalidPacketError, match="empty"):
        packet.parse_inner_plaintext(b"")

    with pytest.raises(InvalidPacketError, match="missing name length"):
        packet.parse_inner_plaintext(b"\x01\x00")

    with pytest.raises(InvalidPacketError, match="truncated filename"):
        packet.parse_inner_plaintext(b"\x01\x00\x05ab")  # declared 5, only 2

    with pytest.raises(InvalidPacketError, match="Unknown inner payload kind"):
        packet.parse_inner_plaintext(b"\x99data")


def test_packet_building_and_parsing_error_paths() -> None:
    """Packet building parameter guards and parsing validation branches."""
    priv, pub = keys.generate_keypair()
    password = "TestPassword123"

    with pytest.raises(CryptoError, match="Salt must be 16 bytes"):
        packet.build_packet("data", password, priv, salt=b"bad_salt")

    with pytest.raises(CryptoError, match="Nonce must be 12 bytes"):
        packet.build_packet("data", password, priv, nonce=b"bad_nonce")

    valid_pkt = packet.build_packet("data", password, priv)

    # Corrupt packet version byte (offset 4)
    bad_version_pkt = bytearray(valid_pkt)
    bad_version_pkt[4] = 0x99
    with pytest.raises(InvalidPacketError, match="Unsupported packet version"):
        packet.parse_and_verify_packet(bytes(bad_version_pkt), password, pub)

    # Declared ct_len mismatch
    bad_len_pkt = bytearray(valid_pkt)
    bad_len_pkt[47] ^= 0x01
    with pytest.raises(InvalidPacketError, match="Packet length mismatch"):
        packet.parse_and_verify_packet(bytes(bad_len_pkt), password, pub)

    # Corrupted compressed payload
    compressed_pkt = bytearray(packet.build_packet("data", password, priv, compress=True))
    # Tamper inside the ciphertext without changing header length
    # Note: AES-GCM will fail on tampered ciphertext, triggering DecryptionFailedError
    compressed_pkt[48] ^= 0x01
    with pytest.raises((DecryptionFailedError, CryptoError)):
        packet.parse_and_verify_packet(bytes(compressed_pkt), password, pub)


def test_signing_invalid_signature_size() -> None:
    """Signing verify returns False when signature is not 64 bytes."""
    _priv, pub = keys.generate_keypair()
    assert signing.verify(pub, b"short_sig", b"data") is False
