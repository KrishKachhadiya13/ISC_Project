"""Serialization and validation for the fixed 13-byte stego stream header."""

import zlib
from dataclasses import dataclass

from app.core.stego.exceptions import NoHiddenDataError

HEADER_MAGIC = b"SGST"
HEADER_VERSION = 0x01
HEADER_PREFIX_BYTES = 9
HEADER_BYTES = 13
HEADER_BITS = HEADER_BYTES * 8
MAX_PAYLOAD_BYTES = (1 << 32) - 1


@dataclass(frozen=True)
class StegoHeader:
    """Validated payload metadata carried before the embedded packet."""

    payload_length: int


def encode_header(payload_length: int) -> bytes:
    """Create a header containing the payload length and CRC32."""
    if not 0 <= payload_length <= MAX_PAYLOAD_BYTES:
        raise ValueError("Payload length must fit an unsigned 32-bit integer.")
    prefix = HEADER_MAGIC + bytes((HEADER_VERSION,)) + payload_length.to_bytes(4, "big")
    checksum = zlib.crc32(prefix).to_bytes(4, "big")
    return prefix + checksum


def decode_header(data: bytes) -> StegoHeader:
    """Validate header magic, version, size, and CRC before returning metadata."""
    if len(data) != HEADER_BYTES:
        raise NoHiddenDataError("No hidden data found.")
    prefix, checksum = data[:HEADER_PREFIX_BYTES], data[HEADER_PREFIX_BYTES:]
    if prefix[:4] != HEADER_MAGIC or prefix[4] != HEADER_VERSION:
        raise NoHiddenDataError("No hidden data found.")
    if zlib.crc32(prefix).to_bytes(4, "big") != checksum:
        raise NoHiddenDataError("No hidden data found.")
    return StegoHeader(payload_length=int.from_bytes(prefix[5:9], "big"))
