"""Tests for binary crypto packet serialization and verify-before-decrypt pipeline."""

from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.crypto.exceptions import (
    DecryptionFailedError,
    InvalidPacketError,
    KeyMismatchError,
    VerificationFailedError,
)
from app.core.crypto.keys import generate_keypair
from app.core.crypto.packet import (
    OVERHEAD_BYTES,
    build_packet,
    format_inner_plaintext,
    parse_and_verify_packet,
)


def test_packet_exact_overhead() -> None:
    """Verify that packet overhead is exactly 128 bytes + inner_plaintext length."""
    priv, _pub = generate_keypair()
    password = "OverheadPassword123"

    for payload_len in [0, 1, 10, 100, 1024]:
        raw_data = b"x" * payload_len
        # format_inner_plaintext adds 1 byte for kind (0x00 for text)
        inner_plaintext = format_inner_plaintext(raw_data, is_file=False)

        packet = build_packet(raw_data, password, priv, is_file=False)
        assert len(packet) == OVERHEAD_BYTES + len(inner_plaintext)


def test_two_encryptions_produce_unique_salts_and_nonces() -> None:
    """Encrypting the same message twice produces distinct salts, nonces, and ciphertexts."""
    priv, _pub = generate_keypair()
    password = "IdenticalPassword123"
    message = "Secret identical payload"

    pkt1 = build_packet(message, password, priv)
    pkt2 = build_packet(message, password, priv)

    assert pkt1 != pkt2

    # Extract salt (bytes 16..32) and nonce (bytes 32..44)
    salt1, nonce1 = pkt1[16:32], pkt1[32:44]
    salt2, nonce2 = pkt2[16:32], pkt2[32:44]

    assert salt1 != salt2
    assert nonce1 != nonce2


def test_round_trip_text_and_unicode() -> None:
    """Verify round trip with empty, short, and complex Unicode text."""
    priv, pub = generate_keypair()
    password = "UnicodePassword123"

    test_cases = [
        "",
        "Hello, World!",
        "StegaGuard: 🔒 🛡️ 🔑 — covert verification",
        "日本語とEnglish and العربية and Russian Русский язык",
    ]

    for text in test_cases:
        packet = build_packet(text, password, priv, is_file=False)
        result = parse_and_verify_packet(packet, password, pub)
        assert result.text == text
        assert result.is_file is False
        assert result.filename is None


def test_round_trip_file_payload() -> None:
    """Verify round trip with file metadata and binary data."""
    priv, pub = generate_keypair()
    password = "FilePassword123"
    file_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    filename = "secret_archive.png"

    packet = build_packet(file_data, password, priv, is_file=True, filename=filename, compress=True)
    result = parse_and_verify_packet(packet, password, pub)

    assert result.is_file is True
    assert result.filename == filename
    assert result.data == file_data


def test_wrong_password_causes_decryption_failed() -> None:
    """Wrong password passes signature verification but fails AEAD tag verification."""
    priv, pub = generate_keypair()
    packet = build_packet("Confidential data", "CorrectPassword123", priv)

    with pytest.raises(DecryptionFailedError):
        parse_and_verify_packet(packet, "WrongPassword123", pub)


def test_wrong_public_key_causes_key_mismatch() -> None:
    """Mismatch in sender public key fingerprint triggers KeyMismatchError immediately."""
    priv1, _pub1 = generate_keypair()
    _priv2, pub2 = generate_keypair()

    packet = build_packet("Message from sender 1", "CommonPassword123", priv1)

    with pytest.raises(KeyMismatchError):
        parse_and_verify_packet(packet, "CommonPassword123", pub2)


def test_bit_flip_tampering_never_attempts_decryption() -> None:
    """CRITICAL SECURITY TEST: Any single bit flipped must fail verification

    and DECRYPTION MUST NEVER BE ATTEMPTED (asserted via mock).
    """
    priv, pub = generate_keypair()
    password = "TamperProofPassword123"
    packet = build_packet("Tamper test payload", password, priv)

    # Test bit flips across various positions: header, ciphertext, signature
    test_positions = [
        0,  # Magic
        4,  # Version
        10,  # Sender fingerprint
        20,  # Salt
        35,  # Nonce
        55,  # Ciphertext
        len(packet) - 1,  # Signature
    ]

    for pos in test_positions:
        tampered = bytearray(packet)
        tampered[pos] ^= 0x01

        with patch("app.core.crypto.aead.decrypt") as mock_decrypt:
            with pytest.raises((VerificationFailedError, InvalidPacketError, KeyMismatchError)):
                parse_and_verify_packet(bytes(tampered), password, pub)

            # Assert decryption was never attempted!
            mock_decrypt.assert_not_called()


def test_large_payload_1mb_round_trip() -> None:
    """Round-trip test for 1 MB arbitrary binary payload."""
    priv, pub = generate_keypair()
    password = "LargePayloadPassword123"
    large_data = b"A" * (1024 * 1024)  # 1 MB

    packet = build_packet(large_data, password, priv, is_file=False)
    result = parse_and_verify_packet(packet, password, pub)
    assert result.data == large_data


@settings(max_examples=30, deadline=None)
@given(st.binary(min_size=0, max_size=4096), st.text(min_size=8, max_size=32))
def test_hypothesis_arbitrary_binary_round_trip(data: bytes, password: str) -> None:
    """Property-based fuzzing: any byte sequence round-trips byte-for-byte."""
    priv, pub = generate_keypair()
    packet = build_packet(data, password, priv, is_file=False)
    result = parse_and_verify_packet(packet, password, pub)
    assert result.data == data
