"""Ed25519 asymmetric keypair management and serialization.

Ed25519 provides deterministic 64-byte signatures over Curve25519 with high performance
and immunity to side-channel cache-timing attacks. Private keys are never persisted in
plaintext; export requires password-authenticated PKCS#8 encryption.
"""

import hashlib
from typing import Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.crypto.exceptions import CryptoError
from app.core.crypto.kdf import validate_password

PUBLIC_KEY_RAW_SIZE: Final[int] = 32
FINGERPRINT_SHORT_SIZE: Final[int] = 8


def generate_keypair() -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Generate a new Ed25519 asymmetric keypair.

    Returns:
        Tuple of (private_key, public_key).
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def export_private_key_pem(private_key: ed25519.Ed25519PrivateKey, password: str) -> str:
    """Export an Ed25519 private key as password-encrypted PKCS#8 PEM.

    Args:
        private_key: Ed25519 private key instance.
        password: User password for key encryption (must be >= 8 chars).

    Returns:
        PEM-encoded string.

    Raises:
        WeakPasswordError: If password is too short.
        CryptoError: If serialization fails.
    """
    validate_password(password)
    try:
        encryption_algorithm = serialization.BestAvailableEncryption(password.encode("utf-8"))
        pem_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption_algorithm,
        )
        return pem_bytes.decode("utf-8")
    except Exception as exc:
        raise CryptoError(f"Failed to export private key: {exc}") from exc


def load_private_key_pem(pem_data: str | bytes, password: str) -> ed25519.Ed25519PrivateKey:
    """Load an encrypted PKCS#8 PEM private key.

    Args:
        pem_data: PEM string or bytes.
        password: Password used during key encryption.

    Returns:
        Loaded Ed25519PrivateKey.

    Raises:
        CryptoError: If password is wrong or PEM data is malformed.
    """
    raw_bytes = pem_data.encode("utf-8") if isinstance(pem_data, str) else pem_data
    try:
        key = serialization.load_pem_private_key(
            raw_bytes,
            password=password.encode("utf-8"),
        )
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise CryptoError("Key is not an Ed25519 private key.")
        return key
    except Exception as exc:
        raise CryptoError(f"Failed to load private key: {exc}") from exc


def export_public_key_pem(public_key: ed25519.Ed25519PublicKey) -> str:
    """Export an Ed25519 public key as SubjectPublicKeyInfo PEM.

    Args:
        public_key: Ed25519 public key instance.

    Returns:
        PEM-encoded string.
    """
    try:
        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem_bytes.decode("utf-8")
    except Exception as exc:
        raise CryptoError(f"Failed to export public key: {exc}") from exc


def load_public_key_pem(pem_data: str | bytes) -> ed25519.Ed25519PublicKey:
    """Load a SubjectPublicKeyInfo PEM public key.

    Args:
        pem_data: PEM string or bytes.

    Returns:
        Loaded Ed25519PublicKey.

    Raises:
        CryptoError: If PEM data is malformed or not an Ed25519 public key.
    """
    raw_bytes = pem_data.encode("utf-8") if isinstance(pem_data, str) else pem_data
    try:
        key = serialization.load_pem_public_key(raw_bytes)
        if not isinstance(key, ed25519.Ed25519PublicKey):
            raise CryptoError("Key is not an Ed25519 public key.")
        return key
    except Exception as exc:
        raise CryptoError(f"Failed to load public key: {exc}") from exc


def get_raw_public_bytes(public_key: ed25519.Ed25519PublicKey) -> bytes:
    """Extract raw 32-byte public key representation.

    Args:
        public_key: Ed25519 public key instance.

    Returns:
        32 raw bytes of the public key.
    """
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def fingerprint(public_key: ed25519.Ed25519PublicKey) -> str:
    """Compute 64-hex SHA-256 fingerprint formatted in 4-character blocks.

    Example output: 'd473 5e3a 265e 16ee ...'

    Args:
        public_key: Ed25519 public key.

    Returns:
        Formatted 64-character hex string with spacing.
    """
    raw_bytes = get_raw_public_bytes(public_key)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    # Chunk into 4-char blocks for user-friendly verification in UI
    return " ".join(digest[i : i + 4] for i in range(0, len(digest), 4))


def fingerprint_short(public_key: ed25519.Ed25519PublicKey) -> bytes:
    """Compute first 8 bytes of SHA-256(raw public key).

    Matches the 8-byte `sender_fp` embedded in the packet header (Section 6.4).

    Args:
        public_key: Ed25519 public key.

    Returns:
        8-byte prefix digest.
    """
    raw_bytes = get_raw_public_bytes(public_key)
    return hashlib.sha256(raw_bytes).digest()[:FINGERPRINT_SHORT_SIZE]
