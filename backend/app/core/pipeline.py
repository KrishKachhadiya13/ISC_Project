"""Stateless sender, receiver, and integrity-verification workflows."""

import base64
import binascii
import hmac
from dataclasses import dataclass
from typing import Any, Literal

from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.crypto import keys, packet, signing
from app.core.crypto import manifest as integrity_manifest
from app.core.crypto.exceptions import CryptoError
from app.core.crypto.packet import PacketPayload, ParsedPacket
from app.core.errors import error_code_for
from app.core.stego.embed import (
    BITS_PER_SAMPLE,
    EmbeddingMethod,
    EmbeddingMode,
    embed,
)
from app.core.stego.exceptions import StegoError
from app.core.stego.extract import extract, extract_auto
from app.core.stego.header import HEADER_BITS
from app.core.stego.image_io import ImageArray, load_image, save_png
from app.core.stego.metrics import calculate_metrics

StageStatus = Literal["passed", "failed", "skipped"]
RECEIVER_STAGES = (
    "read_image",
    "extract_bits",
    "parse_packet",
    "check_sender",
    "verify_signature",
    "derive_key_and_decrypt",
)


@dataclass(frozen=True)
class PipelineStage:
    """Outcome of one ordered receiver-pipeline stage."""

    name: str
    status: StageStatus
    detail: str
    code: str | None = None


@dataclass(frozen=True)
class ReceiverResult:
    """Receiver stages and verified content, if and only if all stages passed."""

    stages: list[PipelineStage]
    verified: bool
    payload: PacketPayload | None = None
    bits_per_sample: int | None = None

    @property
    def plaintext(self) -> str | None:
        """Return verified text only; failures and file payloads expose no text."""
        if self.verified and self.payload is not None and not self.payload.is_file:
            return self.payload.text
        return None

    @property
    def file_data(self) -> bytes | None:
        """Return verified file bytes only."""
        if self.verified and self.payload is not None and self.payload.is_file:
            return self.payload.data
        return None


def sender_pipeline(
    cover: bytes,
    message: str | bytes,
    password: str,
    private_key: ed25519.Ed25519PrivateKey | str | bytes,
    key_password: str,
    method: EmbeddingMethod = "lsb_replace",
    mode: EmbeddingMode = "keyed",
    stego_passphrase: str | None = None,
    *,
    is_file: bool = False,
    filename: str | None = None,
) -> tuple[bytes, dict[str, Any], dict[str, float | int], bytes, list[str]]:
    """Encrypt, sign, embed, and describe a message or file in a cover image.

    Args:
        cover: Encoded cover-image bytes, decoded in memory.
        message: Text or binary content to protect and embed.
        password: Message-encryption password.
        private_key: Ed25519 key or password-encrypted PKCS#8 PEM.
        key_password: Password used to load a PEM private key.
        method: LSB replacement or matching.
        mode: Keyed scatter or sequential placement.
        stego_passphrase: Keyed-mode passphrase; defaults to the message password.
        is_file: Whether ``message`` is a file payload.
        filename: Filename included for file payloads.

    Returns:
        Stego PNG, signed manifest, metrics, amplified difference PNG, and warnings.
    """
    cover_array, warnings = load_image(cover, for_embedding=True)
    if isinstance(private_key, (str, bytes)):
        signing_key = keys.load_private_key_pem(private_key, key_password)
    else:
        signing_key = private_key
    stego_passphrase = stego_passphrase if stego_passphrase is not None else password
    packet_bytes = packet.build_packet(
        message,
        password,
        signing_key,
        is_file=is_file,
        filename=filename,
    )
    stego_array = embed(
        cover_array,
        packet_bytes,
        method=method,
        mode=mode,
        stego_passphrase=stego_passphrase,
    )
    stego_png = save_png(stego_array)

    total_samples = int(cover_array.size)
    header_and_packet_bits = HEADER_BITS + len(packet_bytes) * 8
    salt_bits = 128 if mode == "keyed" else 0
    used_bits = header_and_packet_bits + salt_bits
    if method in {"suniward", "hill"}:
        # STC stores a 32-bit message-length syndrome in a fixed 64-sample block.
        used_bits += 32
    pixel_count = int(cover_array.shape[0] * cover_array.shape[1])
    image_metrics = calculate_metrics(cover_array, stego_array, used_bits)
    metrics: dict[str, float | int] = {
        "mse": image_metrics.mse,
        "psnr": image_metrics.psnr,
        "ssim": image_metrics.ssim,
        "bpp": image_metrics.bpp,
        "bits_changed_pct": image_metrics.fraction_changed * 100,
        "capacity_bits": (
            max(0, total_samples)
            if method in {"suniward", "hill"}
            else max(0, total_samples - salt_bits) * BITS_PER_SAMPLE[method]
        ),
        "used_bits": used_bits,
    }
    manifest = integrity_manifest.create_manifest(
        stego_array=stego_array,
        stego_file_bytes=stego_png,
        method=method,
        mode=mode,
        payload_bytes=len(packet_bytes),
        payload_bpp=(len(packet_bytes) * 8) / pixel_count,
        private_key=signing_key,
        cover_array=cover_array,
    )
    difference_png = save_png(image_metrics.difference_map)
    return stego_png, manifest, metrics, difference_png, warnings


def receiver_pipeline(
    image: bytes,
    password: str,
    public_key: ed25519.Ed25519PublicKey,
    mode: EmbeddingMode = "keyed",
    stego_passphrase: str | None = None,
    bits_per_sample: int | None = None,
) -> ReceiverResult:
    """Run the receiver's ordered verification pipeline without failure plaintext.

    Each failed stage terminates processing and marks every subsequent stage as
    skipped. Decryption is only reached after fingerprint and signature checks.

    ``bits_per_sample=None`` auto-detects 1-bit LSB, 2-LSB, or STC framing; the stream
    header's CRC rejects a wrong guess.
    """
    stages: list[PipelineStage] = []
    image_array: ImageArray | None = None
    payload_bytes: bytes | None = None
    parsed: ParsedPacket | None = None
    payload: PacketPayload | None = None

    try:
        image_array, _warnings = load_image(image)
        stages.append(PipelineStage("read_image", "passed", "Image decoded successfully."))
    except (StegoError, ValueError) as exc:
        return _failed_result(stages, "read_image", exc)

    try:
        if bits_per_sample is None:
            payload_bytes, detected = extract_auto(
                image_array, mode=mode, stego_passphrase=stego_passphrase
            )
        else:
            payload_bytes = extract(
                image_array,
                mode=mode,
                stego_passphrase=stego_passphrase,
                bits_per_sample=bits_per_sample,
            )
            detected = bits_per_sample
        stages.append(
            PipelineStage(
                "extract_bits", "passed", f"Embedded packet extracted ({detected}-bit LSB)."
            )
        )
    except (StegoError, ValueError) as exc:
        return _failed_result(stages, "extract_bits", exc)

    try:
        parsed = packet.parse_packet(payload_bytes)
        stages.append(PipelineStage("parse_packet", "passed", "Packet structure is valid."))
    except CryptoError as exc:
        return _failed_result(stages, "parse_packet", exc)

    try:
        packet.check_sender_fingerprint(parsed, public_key)
        stages.append(PipelineStage("check_sender", "passed", "Sender fingerprint matches."))
    except CryptoError as exc:
        return _failed_result(stages, "check_sender", exc)

    try:
        packet.verify_packet_signature(parsed, public_key)
        stages.append(PipelineStage("verify_signature", "passed", "Packet signature is valid."))
    except CryptoError as exc:
        return _failed_result(stages, "verify_signature", exc)

    try:
        payload = packet.decrypt_verified_packet(parsed, password)
        stages.append(
            PipelineStage("derive_key_and_decrypt", "passed", "Packet authenticated and decrypted.")
        )
    except CryptoError as exc:
        return _failed_result(stages, "derive_key_and_decrypt", exc)
    return ReceiverResult(stages=stages, verified=True, payload=payload, bits_per_sample=detected)


def verify_pipeline(
    image: bytes,
    manifest: dict[str, Any],
    public_key: ed25519.Ed25519PublicKey,
    mode: EmbeddingMode | None = "keyed",
    stego_passphrase: str | None = None,
    bits_per_sample: int | None = None,
) -> dict[str, Any]:
    """Independently verify pixel hash, manifest signature, and packet signature.

    Passing ``mode=None`` skips check C (the embedded packet), which then
    reports ``None``: without the mode the packet cannot be located.
    """
    image_array: ImageArray | None = None
    image_error: str | None = None
    try:
        image_array, _warnings = load_image(image)
    except (StegoError, ValueError) as exc:
        image_error = str(exc)

    pixel_ok = False
    pixel_detail = "Image could not be decoded." if image_error else "Pixel hash mismatch."
    if image_array is not None:
        actual_hash = integrity_manifest.compute_pixel_sha256(image_array)
        expected_hash = manifest.get("stego_pixel_sha256")
        if isinstance(expected_hash, str) and expected_hash.isascii():
            pixel_ok = hmac.compare_digest(actual_hash, expected_hash)
        pixel_detail = "Pixel hash matches." if pixel_ok else "Pixel hash mismatch."

    signature_ok, signature_detail = _verify_manifest_signature(manifest, public_key)
    payload_ok: bool | None = False
    payload_detail = "Embedded packet signature could not be verified."
    if image_array is None:
        payload_ok = None
        payload_detail = "Image could not be decoded."
    elif mode is None:
        payload_ok = None
        payload_detail = "Not checked: no embedding mode was supplied."
    else:
        try:
            if bits_per_sample is None:
                packet_bytes, _depth = extract_auto(
                    image_array, mode=mode, stego_passphrase=stego_passphrase
                )
            else:
                packet_bytes = extract(
                    image_array,
                    mode=mode,
                    stego_passphrase=stego_passphrase,
                    bits_per_sample=bits_per_sample,
                )
            parsed = packet.parse_packet(packet_bytes)
            packet.check_sender_fingerprint(parsed, public_key)
            packet.verify_packet_signature(parsed, public_key)
            payload_ok = True
            payload_detail = "Embedded packet signature is valid."
        except (CryptoError, StegoError, ValueError) as exc:
            payload_detail = str(exc)

    checks = {
        "pixel_hash": {"ok": pixel_ok, "detail": pixel_detail},
        "manifest_signature": {"ok": signature_ok, "detail": signature_detail},
        "payload_signature": {"ok": payload_ok, "detail": payload_detail},
    }
    # A skipped payload check (None) does not block the overall result; the
    # pixel hash and manifest signature already bind the exact image.
    overall_ok = bool(pixel_ok and signature_ok and payload_ok is not False)
    return {"checks": checks, "overall_ok": overall_ok}


def _verify_manifest_signature(
    manifest_data: dict[str, Any],
    public_key: ed25519.Ed25519PublicKey,
) -> tuple[bool, str]:
    """Verify canonical manifest JSON without depending on image hash validity."""
    signature = manifest_data.get("signature")
    if not isinstance(signature, str):
        return False, "Manifest signature is missing or malformed."
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
    except (TypeError, ValueError, binascii.Error):
        return False, "Manifest signature is not valid base64."
    body = {key: value for key, value in manifest_data.items() if key != "signature"}
    try:
        canonical_body = integrity_manifest.canonical_json_encode(body)
    except (TypeError, ValueError):
        return False, "Manifest fields cannot be serialized canonically."
    if not signing.verify(public_key, signature_bytes, canonical_body):
        return False, "Manifest signature is invalid."
    return True, "Manifest signature is valid."


def _failed_result(
    stages: list[PipelineStage],
    failed_stage: str,
    error: Exception,
) -> ReceiverResult:
    """Record the first failed stage and mark all later stages skipped."""
    code = error_code_for(error)
    if failed_stage == "read_image" and code == "INTERNAL":
        # Pillow-level ValueErrors while reading mean the upload is not a usable image.
        code = "INVALID_IMAGE"
    stages.append(PipelineStage(failed_stage, "failed", str(error), code))
    failed_index = RECEIVER_STAGES.index(failed_stage)
    stages.extend(
        PipelineStage(name, "skipped", "Skipped after an earlier stage failed.")
        for name in RECEIVER_STAGES[failed_index + 1 :]
    )
    return ReceiverResult(stages=stages, verified=False)
