"""Ed25519 digital signature signing and verification.

Ed25519 provides 128-bit security level digital signatures over Curve25519.
Signatures are 64 bytes in length and deterministic (do not rely on a random
number generator during signing, eliminating nonce-reuse vulnerabilities).
"""

from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.crypto.exceptions import CryptoError, VerificationFailedError

SIGNATURE_SIZE_BYTES: Final[int] = 64


def sign(private_key: ed25519.Ed25519PrivateKey, data: bytes) -> bytes:
    """Produce a 64-byte Ed25519 digital signature over data.

    Args:
        private_key: Sender's Ed25519 private key.
        data: Arbitrary byte sequence to sign.

    Returns:
        64-byte signature.

    Raises:
        CryptoError: If signing fails.
    """
    try:
        return private_key.sign(data)
    except Exception as exc:
        raise CryptoError(f"Signature generation failed: {exc}") from exc


def verify(public_key: ed25519.Ed25519PublicKey, signature: bytes, data: bytes) -> bool:
    """Verify an Ed25519 signature over data.

    Args:
        public_key: Sender's public key.
        signature: 64-byte signature.
        data: Original byte sequence.

    Returns:
        True if the signature is valid; False otherwise.
    """
    if len(signature) != SIGNATURE_SIZE_BYTES:
        return False

    try:
        public_key.verify(signature, data)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def verify_or_raise(public_key: ed25519.Ed25519PublicKey, signature: bytes, data: bytes) -> None:
    """Verify an Ed25519 signature and raise VerificationFailedError on failure.

    Args:
        public_key: Sender's public key.
        signature: 64-byte signature.
        data: Original byte sequence.

    Raises:
        VerificationFailedError: If signature verification fails.
    """
    if not verify(public_key, signature, data):
        raise VerificationFailedError(
            "Cryptographic signature verification failed: payload has been altered or sender key is invalid."
        )
