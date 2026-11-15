"""Cryptographic primitives, key management, packets, and manifests."""

from app.core.crypto.aead import decrypt, encrypt
from app.core.crypto.exceptions import (
    CryptoError,
    DecryptionFailedError,
    InvalidPacketError,
    KeyMismatchError,
    ManifestVerificationError,
    VerificationFailedError,
    WeakPasswordError,
)
from app.core.crypto.kdf import (
    KDF_ARGON2ID,
    KDF_SCRYPT,
    MIN_PASSWORD_LENGTH,
    derive_key,
    derive_key_argon2id,
    derive_key_scrypt,
    validate_password,
)
from app.core.crypto.keys import (
    export_private_key_pem,
    export_public_key_pem,
    fingerprint,
    fingerprint_short,
    generate_keypair,
    load_private_key_pem,
    load_public_key_pem,
)
from app.core.crypto.manifest import (
    compute_file_sha256,
    compute_pixel_sha256,
    create_manifest,
    verify_manifest,
)
from app.core.crypto.packet import (
    OVERHEAD_BYTES,
    PacketPayload,
    build_packet,
    parse_and_verify_packet,
)
from app.core.crypto.signing import sign, verify, verify_or_raise

__all__ = [
    "CryptoError",
    "DecryptionFailedError",
    "InvalidPacketError",
    "KeyMismatchError",
    "ManifestVerificationError",
    "VerificationFailedError",
    "WeakPasswordError",
    "KDF_ARGON2ID",
    "KDF_SCRYPT",
    "MIN_PASSWORD_LENGTH",
    "derive_key",
    "derive_key_argon2id",
    "derive_key_scrypt",
    "validate_password",
    "encrypt",
    "decrypt",
    "generate_keypair",
    "export_private_key_pem",
    "load_private_key_pem",
    "export_public_key_pem",
    "load_public_key_pem",
    "fingerprint",
    "fingerprint_short",
    "sign",
    "verify",
    "verify_or_raise",
    "build_packet",
    "parse_and_verify_packet",
    "PacketPayload",
    "OVERHEAD_BYTES",
    "create_manifest",
    "verify_manifest",
    "compute_pixel_sha256",
    "compute_file_sha256",
]
