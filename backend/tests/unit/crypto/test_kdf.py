"""Tests for Argon2id and Scrypt key derivation functions."""

import os

import pytest

from app.core.crypto.exceptions import CryptoError, WeakPasswordError
from app.core.crypto.kdf import (
    KDF_ARGON2ID,
    KDF_SCRYPT,
    MIN_PASSWORD_LENGTH,
    derive_key,
    derive_key_argon2id,
    derive_key_scrypt,
    validate_password,
)


def test_validate_password_enforces_minimum_length() -> None:
    """Ensure passwords under MIN_PASSWORD_LENGTH are rejected."""
    with pytest.raises(WeakPasswordError):
        validate_password("short")
    with pytest.raises(WeakPasswordError):
        validate_password("1234567")

    # Minimum valid length (8) passes
    validate_password("12345678")
    validate_password("a" * MIN_PASSWORD_LENGTH)


def test_argon2id_derivation_deterministic() -> None:
    """Argon2id produces identical keys for identical inputs."""
    password = "CorrectHorseBatteryStaple123"
    salt = b"deterministic16b"
    key1 = derive_key_argon2id(password, salt, length=32)
    key2 = derive_key_argon2id(password, salt, length=32)
    assert key1 == key2
    assert len(key1) == 32


def test_argon2id_different_salts_produce_different_keys() -> None:
    """Different salts produce completely different derived keys."""
    password = "CorrectHorseBatteryStaple123"
    salt1 = os.urandom(16)
    salt2 = os.urandom(16)
    key1 = derive_key_argon2id(password, salt1)
    key2 = derive_key_argon2id(password, salt2)
    assert key1 != key2


def test_scrypt_fallback_deterministic() -> None:
    """Scrypt produces identical keys for identical inputs."""
    password = "FallbackPassword123"
    salt = b"scrypt_salt_16bytes"
    key1 = derive_key_scrypt(password, salt, length=32)
    key2 = derive_key_scrypt(password, salt, length=32)
    assert key1 == key2
    assert len(key1) == 32


def test_derive_key_dispatcher() -> None:
    """Dispatcher correctly calls Argon2id and Scrypt based on KDF ID."""
    password = "DispatcherPassword123"
    salt = os.urandom(16)

    key_argon = derive_key(password, salt, kdf_id=KDF_ARGON2ID)
    key_scrypt = derive_key(password, salt, kdf_id=KDF_SCRYPT)

    assert len(key_argon) == 32
    assert len(key_scrypt) == 32
    assert key_argon != key_scrypt

    with pytest.raises(CryptoError, match="Unsupported KDF ID"):
        derive_key(password, salt, kdf_id=0x99)
