"""Tests for Ed25519 digital signature creation and verification."""

import pytest

from app.core.crypto.exceptions import VerificationFailedError
from app.core.crypto.keys import generate_keypair
from app.core.crypto.signing import SIGNATURE_SIZE_BYTES, sign, verify, verify_or_raise


def test_sign_and_verify_round_trip() -> None:
    """Valid signatures verify successfully."""
    priv, pub = generate_keypair()
    data = b"Arbitrary message to sign under Ed25519"

    sig = sign(priv, data)
    assert len(sig) == SIGNATURE_SIZE_BYTES

    assert verify(pub, sig, data) is True
    verify_or_raise(pub, sig, data)  # Should not raise


def test_signature_tampering_detected() -> None:
    """Flipping a bit in signature or message causes verification failure."""
    priv, pub = generate_keypair()
    data = b"Original message content"

    sig = bytearray(sign(priv, data))
    sig[0] ^= 0x01

    assert verify(pub, bytes(sig), data) is False
    with pytest.raises(VerificationFailedError):
        verify_or_raise(pub, bytes(sig), data)

    # Tampering data
    valid_sig = sign(priv, data)
    assert verify(pub, valid_sig, b"Modified message content") is False


def test_wrong_public_key_fails_verification() -> None:
    """Signature verified with a different public key must fail."""
    priv1, _pub1 = generate_keypair()
    _priv2, pub2 = generate_keypair()
    data = b"Signed with key 1"

    sig = sign(priv1, data)
    assert verify(pub2, sig, data) is False
