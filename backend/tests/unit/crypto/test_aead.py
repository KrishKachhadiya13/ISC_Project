"""Tests for AES-256-GCM AEAD encryption and decryption."""

import os

import pytest

from app.core.crypto.aead import (
    KEY_SIZE_BYTES,
    NONCE_SIZE_BYTES,
    TAG_SIZE_BYTES,
    decrypt,
    encrypt,
)
from app.core.crypto.exceptions import CryptoError, DecryptionFailedError


def test_aead_round_trip() -> None:
    """Verify standard encrypt and decrypt round trip."""
    key = os.urandom(KEY_SIZE_BYTES)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    plaintext = b"StegaGuard Confidential Secret Payload"
    aad = b"Authenticated-Header-001"

    ciphertext = encrypt(key, nonce, plaintext, associated_data=aad)
    assert len(ciphertext) == len(plaintext) + TAG_SIZE_BYTES

    recovered = decrypt(key, nonce, ciphertext, associated_data=aad)
    assert recovered == plaintext


def test_aead_ciphertext_tampering_rejected() -> None:
    """Flipping a single bit in ciphertext must cause DecryptionFailedError."""
    key = os.urandom(KEY_SIZE_BYTES)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    plaintext = b"Sensitive message that must not be altered"
    aad = b"AAD"

    ciphertext = bytearray(encrypt(key, nonce, plaintext, associated_data=aad))
    ciphertext[0] ^= 0x01  # Flip bit

    with pytest.raises(DecryptionFailedError):
        decrypt(key, nonce, bytes(ciphertext), associated_data=aad)


def test_aead_aad_tampering_rejected() -> None:
    """Modifying associated data must cause DecryptionFailedError."""
    key = os.urandom(KEY_SIZE_BYTES)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    plaintext = b"Payload with bound header"
    aad = b"Header-V1"

    ciphertext = encrypt(key, nonce, plaintext, associated_data=aad)

    with pytest.raises(DecryptionFailedError):
        decrypt(key, nonce, ciphertext, associated_data=b"Header-V2")


def test_aead_wrong_key_rejected() -> None:
    """Decrypting with incorrect key raises DecryptionFailedError."""
    key1 = os.urandom(KEY_SIZE_BYTES)
    key2 = os.urandom(KEY_SIZE_BYTES)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    plaintext = b"Payload encrypted with key1"

    ciphertext = encrypt(key1, nonce, plaintext)

    with pytest.raises(DecryptionFailedError):
        decrypt(key2, nonce, ciphertext)


def test_aead_invalid_parameter_sizes() -> None:
    """Enforce exact key and nonce length validations."""
    bad_key = b"short_key"
    nonce = os.urandom(NONCE_SIZE_BYTES)

    with pytest.raises(CryptoError, match="key must be exactly 32 bytes"):
        encrypt(bad_key, nonce, b"data")

    with pytest.raises(CryptoError, match="nonce must be exactly 12 bytes"):
        encrypt(os.urandom(KEY_SIZE_BYTES), b"bad_nonce", b"data")

    with pytest.raises(DecryptionFailedError, match="too short"):
        decrypt(os.urandom(KEY_SIZE_BYTES), nonce, b"short")
