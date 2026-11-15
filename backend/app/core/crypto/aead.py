"""Authenticated Encryption with Associated Data (AEAD) using AES-256-GCM.

AES-256-GCM provides both confidentiality and cryptographic integrity verification
via an authentication tag. Associated Authenticated Data (AAD) binds the packet
header to the ciphertext so header fields cannot be tampered with without causing
an authentication failure.
"""

from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.crypto.exceptions import CryptoError, DecryptionFailedError

KEY_SIZE_BYTES: Final[int] = 32  # AES-256
NONCE_SIZE_BYTES: Final[int] = 12  # 96-bit standard GCM nonce
TAG_SIZE_BYTES: Final[int] = 16  # 128-bit authentication tag


def encrypt(
    key: bytes,
    nonce: bytes,
    plaintext: bytes,
    associated_data: bytes = b"",
) -> bytes:
    """Encrypt plaintext using AES-256-GCM with associated data.

    Args:
        key: 32-byte symmetric key.
        nonce: 12-byte unique initialization vector / nonce.
        plaintext: Raw data bytes to encrypt.
        associated_data: Unencrypted header bytes to authenticate.

    Returns:
        Ciphertext with appended 16-byte authentication tag.

    Raises:
        CryptoError: If parameter sizes are invalid or encryption fails.
    """
    if len(key) != KEY_SIZE_BYTES:
        raise CryptoError(f"AES-256 key must be exactly {KEY_SIZE_BYTES} bytes (got {len(key)}).")
    if len(nonce) != NONCE_SIZE_BYTES:
        raise CryptoError(
            f"AES-GCM nonce must be exactly {NONCE_SIZE_BYTES} bytes (got {len(nonce)})."
        )

    try:
        aesgcm = AESGCM(key)
        return aesgcm.encrypt(nonce, plaintext, associated_data)
    except Exception as exc:
        raise CryptoError(f"Encryption failed: {exc}") from exc


def decrypt(
    key: bytes,
    nonce: bytes,
    ciphertext_and_tag: bytes,
    associated_data: bytes = b"",
) -> bytes:
    """Decrypt and verify ciphertext using AES-256-GCM.

    Args:
        key: 32-byte symmetric key.
        nonce: 12-byte initialization vector.
        ciphertext_and_tag: Ciphertext with appended 16-byte authentication tag.
        associated_data: Authenticated associated data bytes.

    Returns:
        Decrypted plaintext bytes.

    Raises:
        DecryptionFailedError: If tag authentication fails (wrong password or corruption).
        CryptoError: If parameter lengths are invalid.
    """
    if len(key) != KEY_SIZE_BYTES:
        raise CryptoError(f"AES-256 key must be exactly {KEY_SIZE_BYTES} bytes (got {len(key)}).")
    if len(nonce) != NONCE_SIZE_BYTES:
        raise CryptoError(
            f"AES-GCM nonce must be exactly {NONCE_SIZE_BYTES} bytes (got {len(nonce)})."
        )
    if len(ciphertext_and_tag) < TAG_SIZE_BYTES:
        raise DecryptionFailedError(
            f"Ciphertext too short to contain {TAG_SIZE_BYTES}-byte authentication tag."
        )

    try:
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data)
    except InvalidTag as exc:
        # Uniform non-leaky error: wrong password, modified ciphertext, or modified AAD
        raise DecryptionFailedError(
            "Decryption failed: corrupted ciphertext, invalid authentication tag, or incorrect password."
        ) from exc
    except Exception as exc:
        raise CryptoError(f"Decryption processing error: {exc}") from exc
