"""Cryptographic exceptions for StegaGuard."""


class CryptoError(Exception):
    """Base exception for all cryptographic operations."""


class VerificationFailedError(CryptoError):
    """Raised when signature verification fails before decryption."""


class KeyMismatchError(CryptoError):
    """Raised when the packet sender fingerprint does not match the provided public key."""


class DecryptionFailedError(CryptoError):
    """Raised when AEAD decryption or authentication tag verification fails."""


class InvalidPacketError(CryptoError):
    """Raised when the packet structure, magic, version, or length is malformed."""


class WeakPasswordError(CryptoError):
    """Raised when a password does not satisfy minimum complexity/length requirements."""


class ManifestVerificationError(CryptoError):
    """Raised when an integrity manifest fails hash or signature verification."""
