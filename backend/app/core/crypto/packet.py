"""Binary crypto packet construction, parsing, and strict verify-before-decrypt pipeline.

Packet Specification (Section 6.4):
Total Overhead = 128 bytes + plaintext length.
------------------------------------------------------------------------------------
Field        Offset  Size   Format   Description
------------------------------------------------------------------------------------
magic             0     4   bytes    b"SGP1"
version           4     1   uint8    0x01
flags             5     1   uint8    bit0: is_file, bit1: zlib_compressed
kdf_id            6     1   uint8    0x01: Argon2id, 0x02: Scrypt
reserved          7     1   uint8    0x00
sender_fp         8     8   bytes    First 8 bytes of SHA-256(raw Ed25519 public key)
salt             16    16   bytes    Random per-message salt for KDF
nonce            32    12   bytes    Random per-message nonce for AES-256-GCM
ct_len           44     4   uint32   Big-endian length of ciphertext (includes 16-byte tag)
ciphertext       48    ct   bytes    AES-256-GCM ciphertext + 16-byte tag
signature   48 + ct    64   bytes    Ed25519 signature over ALL preceding bytes [0 : 48+ct]
------------------------------------------------------------------------------------
Overhead Breakdown:
  Header:             48 bytes
  AES-GCM Auth Tag:   16 bytes (inside ciphertext)
  Ed25519 Signature:  64 bytes
  ----------------------------
  Total Overhead:    128 bytes + inner_plaintext length
"""

import hmac
import os
import struct
import zlib
from dataclasses import dataclass
from typing import Final

from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.crypto import aead, kdf, keys, signing
from app.core.crypto.exceptions import (
    CryptoError,
    DecryptionFailedError,
    InvalidPacketError,
    KeyMismatchError,
)

# Constants
MAGIC: Final[bytes] = b"SGP1"
VERSION: Final[int] = 0x01

# Flags
FLAG_IS_FILE: Final[int] = 0x01
FLAG_COMPRESSED: Final[int] = 0x02

# Sizes
HEADER_SIZE: Final[int] = 48
AAD_SIZE: Final[int] = 44  # magic(4) through nonce(12) = 44 bytes
SIGNATURE_SIZE: Final[int] = 64
SALT_SIZE: Final[int] = 16
NONCE_SIZE: Final[int] = 12
TAG_SIZE: Final[int] = 16
MIN_PACKET_SIZE: Final[int] = HEADER_SIZE + TAG_SIZE + SIGNATURE_SIZE  # 128 bytes
OVERHEAD_BYTES: Final[int] = 128


@dataclass(frozen=True)
class PacketPayload:
    """Decrypted and verified packet content."""

    data: bytes
    is_file: bool
    filename: str | None = None

    @property
    def text(self) -> str:
        """Decode payload data as UTF-8 string."""
        return self.data.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class ParsedPacket:
    """Structurally validated packet fields prior to sender authentication."""

    packet_bytes: bytes
    flags: int
    kdf_id: int
    sender_fingerprint: bytes
    salt: bytes
    nonce: bytes
    ciphertext: bytes
    signature: bytes

    @property
    def signed_data(self) -> bytes:
        """Return the exact packet bytes covered by the Ed25519 signature."""
        return self.packet_bytes[:-SIGNATURE_SIZE]

    @property
    def associated_data(self) -> bytes:
        """Return packet header bytes authenticated as AES-GCM associated data."""
        return self.packet_bytes[:AAD_SIZE]


def format_inner_plaintext(
    data: bytes, is_file: bool = False, filename: str | None = None
) -> bytes:
    """Format payload according to the inner plaintext specification.

    Inner format:
        kind (1 byte: 0=text, 1=file) || [name_len(2) || name(UTF-8) if file] || data
    """
    if is_file:
        name_bytes = (filename or "unnamed_file").encode("utf-8")
        if len(name_bytes) > 65535:
            raise CryptoError("Filename exceeds maximum length of 65535 bytes.")
        name_len = struct.pack(">H", len(name_bytes))
        return b"\x01" + name_len + name_bytes + data
    else:
        return b"\x00" + data


def parse_inner_plaintext(inner_bytes: bytes) -> tuple[bytes, bool, str | None]:
    """Parse inner plaintext format into (data, is_file, filename)."""
    if len(inner_bytes) < 1:
        raise InvalidPacketError("Inner plaintext is empty.")

    kind = inner_bytes[0]
    if kind == 0:  # Text
        return inner_bytes[1:], False, None
    elif kind == 1:  # File
        if len(inner_bytes) < 3:
            raise InvalidPacketError("Malformed file inner payload (missing name length).")
        name_len = struct.unpack(">H", inner_bytes[1:3])[0]
        if len(inner_bytes) < 3 + name_len:
            raise InvalidPacketError("Malformed file inner payload (truncated filename).")
        filename = inner_bytes[3 : 3 + name_len].decode("utf-8", errors="replace")
        data = inner_bytes[3 + name_len :]
        return data, True, filename
    else:
        raise InvalidPacketError(f"Unknown inner payload kind: {kind}")


def build_packet(
    data: bytes | str,
    password: str,
    private_key: ed25519.Ed25519PrivateKey,
    is_file: bool = False,
    filename: str | None = None,
    compress: bool = False,
    kdf_id: int = kdf.KDF_ARGON2ID,
    salt: bytes | None = None,
    nonce: bytes | None = None,
) -> bytes:
    """Assemble, encrypt, and digitally sign a StegaGuard crypto packet.

    Args:
        data: Plaintext data (bytes or str).
        password: Password for key derivation.
        private_key: Sender's Ed25519 private key.
        is_file: Whether payload represents an attached file.
        filename: Optional filename if is_file is True.
        compress: Whether to zlib-compress inner plaintext before encryption.
        kdf_id: KDF algorithm ID (0x01 Argon2id, 0x02 Scrypt).
        salt: Optional 16-byte salt (generated randomly if None).
        nonce: Optional 12-byte nonce (generated randomly if None).

    Returns:
        Fully assembled and signed binary packet.
    """
    raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
    inner_plaintext = format_inner_plaintext(raw_bytes, is_file=is_file, filename=filename)

    flags = 0
    if is_file:
        flags |= FLAG_IS_FILE
    if compress:
        flags |= FLAG_COMPRESSED
        inner_plaintext = zlib.compress(inner_plaintext)

    # Cryptographic unique salt and nonce generation (Section 5.2)
    salt_bytes = salt if salt is not None else os.urandom(SALT_SIZE)
    nonce_bytes = nonce if nonce is not None else os.urandom(NONCE_SIZE)

    if len(salt_bytes) != SALT_SIZE:
        raise CryptoError(f"Salt must be {SALT_SIZE} bytes (got {len(salt_bytes)}).")
    if len(nonce_bytes) != NONCE_SIZE:
        raise CryptoError(f"Nonce must be {NONCE_SIZE} bytes (got {len(nonce_bytes)}).")

    # Derive symmetric key
    key = kdf.derive_key(password, salt_bytes, kdf_id=kdf_id, length=aead.KEY_SIZE_BYTES)

    # Sender public key fingerprint short (8 bytes)
    sender_fp = keys.fingerprint_short(private_key.public_key())

    # Build AAD: magic(4) + version(1) + flags(1) + kdf_id(1) + reserved(1) + sender_fp(8) + salt(16) + nonce(12)
    aad = (
        MAGIC
        + struct.pack(">BBBB", VERSION, flags, kdf_id, 0x00)
        + sender_fp
        + salt_bytes
        + nonce_bytes
    )
    assert len(aad) == AAD_SIZE

    # AES-256-GCM encryption
    ciphertext = aead.encrypt(key, nonce_bytes, inner_plaintext, associated_data=aad)
    ct_len_bytes = struct.pack(">I", len(ciphertext))

    # Pre-signature packet bytes (48 + len(ciphertext))
    packet_before_sig = aad + ct_len_bytes + ciphertext
    assert len(packet_before_sig) == HEADER_SIZE + len(ciphertext)

    # Ed25519 digital signature over ALL preceding bytes of the packet
    sig = signing.sign(private_key, packet_before_sig)
    assert len(sig) == SIGNATURE_SIZE

    return packet_before_sig + sig


def parse_and_verify_packet(
    packet_bytes: bytes,
    password: str,
    public_key: ed25519.Ed25519PublicKey,
) -> PacketPayload:
    """Parse, verify signature, and decrypt a StegaGuard packet.

    CRITICAL SECURITY INVARIANT (Section 5.2):
    Verification occurs BEFORE decryption. If the signature verification fails,
    an exception is immediately raised and decryption/KDF is NEVER executed.

    Args:
        packet_bytes: Binary packet data.
        password: User password for symmetric decryption.
        public_key: Sender's Ed25519 public key.

    Returns:
        Verified PacketPayload containing decrypted data and metadata.

    Raises:
        InvalidPacketError: If packet formatting, magic, or length is malformed.
        KeyMismatchError: If the sender fingerprint does not match the public key.
        VerificationFailedError: If signature verification fails (stops before decrypt!).
        DecryptionFailedError: If AES-GCM tag verification fails.
    """
    parsed = parse_packet(packet_bytes)
    check_sender_fingerprint(parsed, public_key)
    verify_packet_signature(parsed, public_key)
    return decrypt_verified_packet(parsed, password)


def parse_packet(packet_bytes: bytes) -> ParsedPacket:
    """Validate packet structure and expose fields for staged receiver flows.

    This function performs no key derivation, signature verification, or
    decryption. Callers must run ``check_sender_fingerprint`` and
    ``verify_packet_signature`` before ``decrypt_verified_packet``.
    """
    if len(packet_bytes) < MIN_PACKET_SIZE:
        raise InvalidPacketError(
            f"Packet too short: {len(packet_bytes)} bytes (minimum {MIN_PACKET_SIZE} bytes)."
        )

    magic = packet_bytes[:4]
    if magic != MAGIC:
        raise InvalidPacketError(f"Invalid packet magic bytes: {magic!r} (expected {MAGIC!r}).")

    version, flags, kdf_id, _reserved = struct.unpack(">BBBB", packet_bytes[4:8])
    if version != VERSION:
        raise InvalidPacketError(f"Unsupported packet version: {version:#04x}.")

    ct_len = struct.unpack(">I", packet_bytes[44:48])[0]
    expected_total_len = HEADER_SIZE + ct_len + SIGNATURE_SIZE
    if len(packet_bytes) != expected_total_len:
        raise InvalidPacketError(
            f"Packet length mismatch: declared {expected_total_len} bytes, got {len(packet_bytes)}."
        )

    ciphertext_end = HEADER_SIZE + ct_len
    return ParsedPacket(
        packet_bytes=packet_bytes,
        flags=flags,
        kdf_id=kdf_id,
        sender_fingerprint=packet_bytes[8:16],
        salt=packet_bytes[16:32],
        nonce=packet_bytes[32:44],
        ciphertext=packet_bytes[HEADER_SIZE:ciphertext_end],
        signature=packet_bytes[ciphertext_end:],
    )


def check_sender_fingerprint(
    parsed: ParsedPacket,
    public_key: ed25519.Ed25519PublicKey,
) -> None:
    """Constant-time compare the packet's sender fingerprint with the public key."""
    expected = keys.fingerprint_short(public_key)
    if not hmac.compare_digest(parsed.sender_fingerprint, expected):
        raise KeyMismatchError("Packet sender fingerprint does not match the provided public key.")


def verify_packet_signature(
    parsed: ParsedPacket,
    public_key: ed25519.Ed25519PublicKey,
) -> None:
    """Verify the packet's Ed25519 signature without deriving or using an AES key."""
    signing.verify_or_raise(public_key, parsed.signature, parsed.signed_data)


def decrypt_verified_packet(parsed: ParsedPacket, password: str) -> PacketPayload:
    """Derive the AEAD key and decrypt a packet whose signature was verified."""
    key = kdf.derive_key(password, parsed.salt, kdf_id=parsed.kdf_id, length=aead.KEY_SIZE_BYTES)
    inner_plaintext = aead.decrypt(
        key,
        parsed.nonce,
        parsed.ciphertext,
        associated_data=parsed.associated_data,
    )

    if parsed.flags & FLAG_COMPRESSED:
        try:
            inner_plaintext = zlib.decompress(inner_plaintext)
        except Exception as exc:
            raise DecryptionFailedError(f"Corrupted compressed payload: {exc}") from exc

    # 7. Parse inner format
    data, is_file, filename = parse_inner_plaintext(inner_plaintext)
    return PacketPayload(data=data, is_file=is_file, filename=filename)
