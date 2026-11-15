"""Key derivation functions (KDF) implementing Argon2id with Scrypt fallback.

Argon2id is chosen as the primary KDF because it provides memory-hard protection
against both GPU and ASIC brute-force attacks, combining Argon2d's resistance to
GPU cracking with Argon2i's resistance to side-channel timing attacks.
"""

from typing import Final

import argon2.low_level
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.core.crypto.exceptions import CryptoError, WeakPasswordError

# KDF identifiers matching packet specification (Section 6.4)
KDF_ARGON2ID: Final[int] = 0x01
KDF_SCRYPT: Final[int] = 0x02

# Minimum password length enforced across all cryptographic operations
MIN_PASSWORD_LENGTH: Final[int] = 8

# Argon2id parameters (Section 6.4: t=3, m=64 MiB, p=4)
ARGON2_TIME_COST: Final[int] = 3
ARGON2_MEMORY_COST_KIB: Final[int] = 65536  # 64 MiB
ARGON2_PARALLELISM: Final[int] = 4

# Scrypt fallback parameters (Section 6.4: n=2**15, r=8, p=1)
SCRYPT_N: Final[int] = 32768  # 2**15
SCRYPT_R: Final[int] = 8
SCRYPT_P: Final[int] = 1


def validate_password(password: str) -> None:
    """Enforce minimum password length requirement.

    Args:
        password: User-provided passphrase.

    Raises:
        WeakPasswordError: If the password is shorter than MIN_PASSWORD_LENGTH.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long (got {len(password)})."
        )


def derive_key_argon2id(password: str, salt: bytes, length: int = 32) -> bytes:
    """Derive a symmetric encryption key using Argon2id.

    Args:
        password: User passphrase.
        salt: Cryptographic random salt (typically 16 bytes).
        length: Desired output key length in bytes (default 32 for AES-256).

    Returns:
        Derived key bytes.

    Raises:
        CryptoError: If key derivation fails.
    """
    validate_password(password)
    try:
        # Argon2id combines data-dependent (Argon2d) and data-independent (Argon2i) memory passes
        return argon2.low_level.hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_COST_KIB,
            parallelism=ARGON2_PARALLELISM,
            hash_len=length,
            type=argon2.low_level.Type.ID,
        )
    except Exception as exc:
        raise CryptoError(f"Argon2id derivation failed: {exc}") from exc


def derive_key_scrypt(password: str, salt: bytes, length: int = 32) -> bytes:
    """Derive a symmetric encryption key using Scrypt (fallback mode).

    Args:
        password: User passphrase.
        salt: Cryptographic random salt.
        length: Desired output key length in bytes (default 32 for AES-256).

    Returns:
        Derived key bytes.

    Raises:
        CryptoError: If key derivation fails.
    """
    validate_password(password)
    try:
        kdf = Scrypt(
            salt=salt,
            length=length,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
        return kdf.derive(password.encode("utf-8"))
    except Exception as exc:
        raise CryptoError(f"Scrypt derivation failed: {exc}") from exc


def derive_key(password: str, salt: bytes, kdf_id: int = KDF_ARGON2ID, length: int = 32) -> bytes:
    """Dispatch key derivation based on the specified KDF algorithm identifier.

    Args:
        password: User passphrase.
        salt: Random per-message salt.
        kdf_id: Algorithm ID (0x01 for Argon2id, 0x02 for Scrypt).
        length: Output key length in bytes.

    Returns:
        Derived symmetric key bytes.

    Raises:
        CryptoError: If an unknown KDF ID is supplied or derivation fails.
    """
    if kdf_id == KDF_ARGON2ID:
        return derive_key_argon2id(password, salt, length)
    elif kdf_id == KDF_SCRYPT:
        return derive_key_scrypt(password, salt, length)
    else:
        raise CryptoError(f"Unsupported KDF ID: {kdf_id:#04x}")
