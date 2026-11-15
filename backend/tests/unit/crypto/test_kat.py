"""Known-Answer Tests (KAT) for Ed25519 (RFC 8032) and AES-256-GCM (NIST SP 800-38D)."""

from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.crypto import aead, signing


def test_rfc8032_ed25519_vector_1() -> None:
    """RFC 8032 Section 7.1 Test Vector 1 (Empty message)."""
    priv_seed_hex = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
    pub_hex = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    expected_sig_hex = (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )

    priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_seed_hex))
    pub_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))

    msg = b""
    actual_sig = signing.sign(priv_key, msg)
    assert actual_sig.hex() == expected_sig_hex
    assert signing.verify(pub_key, actual_sig, msg) is True


def test_rfc8032_ed25519_vector_2() -> None:
    """RFC 8032 Section 7.1 Test Vector 2 (1-byte message 'r' / 0x72)."""
    priv_seed_hex = "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"
    pub_hex = "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
    msg_hex = "72"
    expected_sig_hex = (
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"
    )

    priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_seed_hex))
    pub_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))

    msg = bytes.fromhex(msg_hex)
    actual_sig = signing.sign(priv_key, msg)
    assert actual_sig.hex() == expected_sig_hex
    assert signing.verify(pub_key, actual_sig, msg) is True


def test_nist_sp800_38d_aes256_gcm_test_case_13() -> None:
    """NIST SP 800-38D Test Case 13 (AES-256-GCM, empty plaintext, empty AAD)."""
    key = bytes(32)  # 32 bytes 0x00
    iv = bytes(12)  # 12 bytes 0x00
    plaintext = b""
    expected_tag_hex = "530f8afbc74536b9a963b4f1c4cb738b"

    ciphertext_and_tag = aead.encrypt(key, iv, plaintext)
    assert ciphertext_and_tag.hex() == expected_tag_hex

    recovered = aead.decrypt(key, iv, ciphertext_and_tag)
    assert recovered == plaintext


def test_nist_sp800_38d_aes256_gcm_test_case_14() -> None:
    """NIST SP 800-38D Test Case 14 (AES-256-GCM, 16-byte plaintext)."""
    key = bytes(32)  # 32 bytes 0x00
    iv = bytes(12)  # 12 bytes 0x00
    plaintext = bytes(16)  # 16 bytes 0x00
    expected_ct_hex = "cea7403d4d606b6e074ec5d3baf39d18"
    expected_tag_hex = "d0d1c8a799996bf0265b98b5d48ab919"
    expected_combined = expected_ct_hex + expected_tag_hex

    ciphertext_and_tag = aead.encrypt(key, iv, plaintext)
    assert ciphertext_and_tag.hex() == expected_combined

    recovered = aead.decrypt(key, iv, ciphertext_and_tag)
    assert recovered == plaintext
