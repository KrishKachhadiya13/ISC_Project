"""Tests for Ed25519 key generation, serialization, and fingerprinting."""

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.crypto.exceptions import CryptoError, WeakPasswordError
from app.core.crypto.keys import (
    export_private_key_pem,
    export_public_key_pem,
    fingerprint,
    fingerprint_short,
    generate_keypair,
    get_raw_public_bytes,
    load_private_key_pem,
    load_public_key_pem,
)


def test_keypair_generation() -> None:
    """generate_keypair returns valid Ed25519 private and public keys."""
    priv, pub = generate_keypair()
    assert isinstance(priv, ed25519.Ed25519PrivateKey)
    assert isinstance(pub, ed25519.Ed25519PublicKey)
    assert len(get_raw_public_bytes(pub)) == 32


def test_private_key_pem_round_trip() -> None:
    """Private key exports to encrypted PKCS#8 PEM and reloads with password."""
    priv, _pub = generate_keypair()
    password = "StrongKeyPassword123"

    pem = export_private_key_pem(priv, password)
    assert "-----BEGIN ENCRYPTED PRIVATE KEY-----" in pem

    reloaded = load_private_key_pem(pem, password)
    assert isinstance(reloaded, ed25519.Ed25519PrivateKey)

    # Reload with wrong password fails
    with pytest.raises(CryptoError):
        load_private_key_pem(pem, "WrongPassword123")


def test_private_key_export_rejects_weak_password() -> None:
    """Key password must be at least 8 characters."""
    priv, _pub = generate_keypair()
    with pytest.raises(WeakPasswordError):
        export_private_key_pem(priv, "short")


def test_public_key_pem_round_trip() -> None:
    """Public key exports to SubjectPublicKeyInfo PEM and reloads."""
    _priv, pub = generate_keypair()
    pem = export_public_key_pem(pub)
    assert "-----BEGIN PUBLIC KEY-----" in pem

    reloaded = load_public_key_pem(pem)
    assert isinstance(reloaded, ed25519.Ed25519PublicKey)
    assert get_raw_public_bytes(reloaded) == get_raw_public_bytes(pub)


def test_fingerprints() -> None:
    """Fingerprints are correctly computed and formatted."""
    _priv, pub = generate_keypair()

    fp = fingerprint(pub)
    blocks = fp.split(" ")
    assert len(blocks) == 16  # 16 blocks of 4 hex chars = 64 hex chars
    assert all(len(b) == 4 for b in blocks)

    short_fp = fingerprint_short(pub)
    assert len(short_fp) == 8
    # Short fp matches first 8 bytes (16 hex chars) of full fingerprint
    assert short_fp.hex() == "".join(blocks)[:16]
