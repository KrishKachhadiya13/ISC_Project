"""Signed integrity manifest creation and verification.

The manifest is a detached JSON document produced after embedding. It binds
the pixel contents, dimensions, steganographic parameters, and payload size
to the sender's Ed25519 identity. Canonical JSON serialization guarantees
deterministic signature verification across diverse JSON encoders.
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.crypto import keys, signing

MANIFEST_VERSION: int = 1


def compute_pixel_sha256(array: np.ndarray) -> str:
    """Compute deterministic SHA-256 hash over pixel array data.

    Format: SHA-256(b"{H},{W},{C},uint8|" + array.tobytes())
    This ensures that image dimensions, channels, and pixel ordering are
    cryptographically bound, while remaining immune to lossless PNG re-compression.

    Args:
        array: NumPy array of shape (H, W) or (H, W, C), uint8.

    Returns:
        64-character lowercase hexadecimal hash.
    """
    if array.dtype != np.uint8:
        raise ValueError(f"Array must be uint8 (got {array.dtype}).")

    if array.ndim == 2:
        h, w = array.shape
        c = 1
    elif array.ndim == 3:
        h, w, c = array.shape
    else:
        raise ValueError(f"Unsupported array dimensions: {array.ndim} (must be 2 or 3).")

    prefix = f"{h},{w},{c},uint8|".encode("ascii")
    hasher = hashlib.sha256(prefix)
    hasher.update(array.tobytes())
    return hasher.hexdigest()


def compute_file_sha256(file_bytes: bytes) -> str:
    """Compute SHA-256 hash over exact raw file bytes."""
    return hashlib.sha256(file_bytes).hexdigest()


def canonical_json_encode(data: dict[str, Any]) -> bytes:
    """Encode dictionary into canonical JSON bytes for deterministic signing.

    Keys are sorted, whitespace separators are minimized (',', ':'),
    and unicode characters are not escaped.

    Args:
        data: Dictionary to encode.

    Returns:
        Canonical UTF-8 encoded JSON bytes.
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def create_manifest(
    stego_array: np.ndarray,
    stego_file_bytes: bytes,
    method: str,
    mode: str,
    payload_bytes: int,
    payload_bpp: float,
    private_key: ed25519.Ed25519PrivateKey,
    cover_array: np.ndarray | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create and digitally sign an integrity manifest.

    Args:
        stego_array: Stego image pixel array.
        stego_file_bytes: Exact bytes of the saved stego PNG file.
        method: Stego method ('lsb_replace' or 'lsb_match').
        mode: Stego mode ('keyed' or 'sequential').
        payload_bytes: Number of hidden bytes embedded.
        payload_bpp: Embedded bits per pixel.
        private_key: Sender's Ed25519 private key.
        cover_array: Optional original cover pixel array.
        created_at: Optional ISO 8601 timestamp string (generated if None).

    Returns:
        Dictionary containing manifest fields and base64-encoded signature.
    """
    if stego_array.ndim == 2:
        h, w = stego_array.shape
        c = 1
    elif stego_array.ndim == 3:
        h, w, c = stego_array.shape
    else:
        raise ValueError(f"Invalid array shape {stego_array.shape}")

    timestamp = created_at or datetime.now(UTC).isoformat()
    stego_pixel_hash = compute_pixel_sha256(stego_array)
    cover_pixel_hash = compute_pixel_sha256(cover_array) if cover_array is not None else None
    stego_file_hash = compute_file_sha256(stego_file_bytes)
    sender_fp = keys.fingerprint(private_key.public_key()).replace(" ", "")

    manifest_body: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "created_at": timestamp,
        "cover_pixel_sha256": cover_pixel_hash,
        "stego_pixel_sha256": stego_pixel_hash,
        "stego_file_sha256": stego_file_hash,
        "dimensions": [w, h],
        "channels": c,
        "method": method,
        "mode": mode,
        "payload_bytes": payload_bytes,
        "payload_bpp": float(f"{payload_bpp:.6f}"),
        "sender_fingerprint": sender_fp,
    }

    # Digitally sign canonical JSON representation of all fields
    canonical_bytes = canonical_json_encode(manifest_body)
    sig_bytes = signing.sign(private_key, canonical_bytes)
    sig_b64 = base64.b64encode(sig_bytes).decode("ascii")

    manifest = dict(manifest_body)
    manifest["signature"] = sig_b64
    return manifest


def verify_manifest(
    manifest: dict[str, Any],
    stego_array: np.ndarray,
    public_key: ed25519.Ed25519PublicKey,
    stego_file_bytes: bytes | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Verify manifest signature, pixel SHA-256, and optional file SHA-256.

    Args:
        manifest: Manifest dictionary with 'signature' field.
        stego_array: Image array to test against manifest.
        public_key: Sender's public key.
        stego_file_bytes: Optional raw PNG bytes to check file hash.

    Returns:
        Tuple of (overall_valid, verification_details_dict).
    """
    if "signature" not in manifest:
        return False, {"error": "Missing signature in manifest."}

    sig_b64 = manifest["signature"]
    try:
        sig_bytes = base64.b64decode(sig_b64)
    except Exception as exc:
        return False, {"error": f"Invalid base64 signature: {exc}"}

    # Extract all fields except signature for canonical verification
    body = {k: v for k, v in manifest.items() if k != "signature"}
    canonical_bytes = canonical_json_encode(body)

    # 1. Verify Ed25519 signature
    sig_ok = signing.verify(public_key, sig_bytes, canonical_bytes)

    # 2. Verify pixel SHA-256 (constant-time comparison)
    actual_pixel_hash = compute_pixel_sha256(stego_array)
    expected_pixel_hash = manifest.get("stego_pixel_sha256", "")
    pixel_ok = hmac.compare_digest(actual_pixel_hash, expected_pixel_hash)

    # 3. Optional file SHA-256 verification
    file_ok: bool | None = None
    if stego_file_bytes is not None and "stego_file_sha256" in manifest:
        actual_file_hash = compute_file_sha256(stego_file_bytes)
        expected_file_hash = manifest["stego_file_sha256"]
        file_ok = hmac.compare_digest(actual_file_hash, expected_file_hash)

    # 4. Sender fingerprint matching check
    expected_fp = keys.fingerprint(public_key).replace(" ", "")
    manifest_fp = manifest.get("sender_fingerprint", "").replace(" ", "")
    fp_ok = hmac.compare_digest(manifest_fp, expected_fp)

    overall_ok = sig_ok and pixel_ok and fp_ok and (file_ok is None or file_ok)

    details = {
        "signature_valid": sig_ok,
        "pixel_hash_valid": pixel_ok,
        "fingerprint_valid": fp_ok,
        "file_hash_valid": file_ok,
        "overall_valid": overall_ok,
        "computed_pixel_hash": actual_pixel_hash,
        "expected_pixel_hash": expected_pixel_hash,
    }
    return overall_ok, details
