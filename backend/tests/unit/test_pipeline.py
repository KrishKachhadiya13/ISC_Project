"""End-to-end tests for secure sender, receiver, and verification pipelines."""

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from app.cli import main
from app.core.crypto import keys
from app.core.pipeline import RECEIVER_STAGES, receiver_pipeline, sender_pipeline, verify_pipeline
from app.core.stego.image_io import load_image, save_png

PASSWORD = "MessagePassword123"


def _cover_png(seed: int = 17) -> bytes:
    """Create a deterministic, lossless cover image for pipeline tests."""
    pixels = np.random.default_rng(seed).integers(0, 256, (96, 96, 3), dtype=np.uint8)
    return save_png(pixels)


def _send(
    cover: bytes | None = None,
    message: str | bytes = "pipeline secret",
    *,
    mode: str = "keyed",
    method: str = "lsb_replace",
) -> tuple[bytes, dict[str, Any], Any, Any, Any, Any, Any]:
    """Create one complete sender output using an ephemeral Ed25519 key."""
    private_key, public_key = keys.generate_keypair()
    result = sender_pipeline(
        _cover_png() if cover is None else cover,
        message,
        PASSWORD,
        private_key,
        "unused-with-key-object",
        method=method,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
    )
    return (*result, public_key, private_key)


def test_sender_receiver_and_verify_pipeline_round_trip() -> None:
    """Sender output round-trips and all three detached integrity checks pass."""
    stego_png, manifest, metrics, diff_png, warnings, public_key, _private_key = _send(
        message="StegaGuard pipeline 🔐"
    )
    result = receiver_pipeline(stego_png, PASSWORD, public_key, stego_passphrase=PASSWORD)

    assert result.verified
    assert result.plaintext == "StegaGuard pipeline 🔐"
    assert result.file_data is None
    assert [stage.name for stage in result.stages] == list(RECEIVER_STAGES)
    assert all(stage.status == "passed" for stage in result.stages)
    assert set(metrics) == {
        "mse",
        "psnr",
        "ssim",
        "bpp",
        "bits_changed_pct",
        "capacity_bits",
        "used_bits",
    }
    assert diff_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert stego_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert warnings == []
    checks = verify_pipeline(stego_png, manifest, public_key, stego_passphrase=PASSWORD)
    assert checks["overall_ok"] is True
    assert all(check["ok"] is True for check in checks["checks"].values())


@pytest.mark.parametrize(
    ("mode", "method"),
    [
        ("keyed", "lsb_replace"),
        ("keyed", "lsb_match"),
        ("sequential", "lsb_replace"),
        ("sequential", "lsb_match"),
    ],
)
def test_sender_receiver_cross_product(mode: str, method: str) -> None:
    """Both embedding methods and modes work through the complete pipeline."""
    stego_png, _manifest, _metrics, _diff, _warnings, public_key, _private_key = _send(
        message="method and mode",
        mode=mode,
        method=method,
    )
    result = receiver_pipeline(
        stego_png,
        PASSWORD,
        public_key,
        mode=mode,  # type: ignore[arg-type]
        stego_passphrase=PASSWORD if mode == "keyed" else None,
    )
    assert result.verified
    assert result.plaintext == "method and mode"


def test_file_payload_round_trip() -> None:
    """File bytes and filename survive encryption, embedding, and extraction."""
    content = b"\x00\xffbinary file\x10"
    private_key, public_key = keys.generate_keypair()
    stego_png, _manifest, _metrics, _diff, _warnings = sender_pipeline(
        _cover_png(),
        content,
        PASSWORD,
        private_key,
        "unused-with-key-object",
        is_file=True,
        filename="payload.bin",
    )
    result = receiver_pipeline(stego_png, PASSWORD, public_key, stego_passphrase=PASSWORD)
    assert result.verified
    assert result.plaintext is None
    assert result.file_data == content
    assert result.payload is not None
    assert result.payload.filename == "payload.bin"


def test_wrong_password_fails_only_at_decrypt_and_never_returns_plaintext() -> None:
    """Wrong message passwords fail after signature checks and expose no payload."""
    stego_png, _manifest, _metrics, _diff, _warnings, public_key, _private_key = _send()
    result = receiver_pipeline(
        stego_png,
        "IncorrectPassword123",
        public_key,
        stego_passphrase=PASSWORD,
    )
    assert not result.verified
    assert [stage.name for stage in result.stages] == list(RECEIVER_STAGES)
    assert [stage.status for stage in result.stages] == ["passed"] * 5 + ["failed"]
    assert result.payload is None
    assert result.plaintext is None
    assert result.file_data is None


def test_wrong_sender_key_fails_before_signature_and_decryption() -> None:
    """A wrong public key stops at sender fingerprint comparison."""
    stego_png, _manifest, _metrics, _diff, _warnings, _public_key, _private_key = _send()
    _wrong_private, wrong_public = keys.generate_keypair()
    result = receiver_pipeline(
        stego_png,
        PASSWORD,
        wrong_public,
        stego_passphrase=PASSWORD,
    )
    assert [stage.status for stage in result.stages] == ["passed"] * 3 + [
        "failed",
        "skipped",
        "skipped",
    ]
    assert result.stages[3].name == "check_sender"
    assert result.payload is None
    assert result.plaintext is None


@pytest.mark.parametrize("failure", ["wrong_mode", "wrong_stego_key"])
def test_extract_failures_stop_pipeline_without_plaintext(failure: str) -> None:
    """Mode and stego-key failures stop before packet parsing."""
    stego_png, _manifest, _metrics, _diff, _warnings, public_key, _private_key = _send()
    mode = "sequential" if failure == "wrong_mode" else "keyed"
    passphrase = "wrong stego password" if failure == "wrong_stego_key" else None
    result = receiver_pipeline(
        stego_png,
        PASSWORD,
        public_key,
        mode=mode,  # type: ignore[arg-type]
        stego_passphrase=passphrase,
    )
    assert result.stages[1].name == "extract_bits"
    assert result.stages[1].status == "failed"
    assert all(stage.status == "skipped" for stage in result.stages[2:])
    assert result.payload is None
    assert result.plaintext is None


def test_malformed_and_truncated_image_fail_without_plaintext() -> None:
    """Truncated and non-image bytes stop at image loading."""
    stego_png, _manifest, _metrics, _diff, _warnings, public_key, _private_key = _send()
    for damaged in (b"not an image", stego_png[: len(stego_png) // 2]):
        result = receiver_pipeline(damaged, PASSWORD, public_key)
        assert result.stages[0].name == "read_image"
        assert result.stages[0].status == "failed"
        assert all(stage.status == "skipped" for stage in result.stages[1:])
        assert result.payload is None
        assert result.plaintext is None


def test_single_pixel_manifest_tamper_and_embedded_tamper_are_detected() -> None:
    """Pixel-hash and packet extraction detect independent image modifications."""
    stego_png, manifest, _metrics, _diff, _warnings, public_key, _private_key = _send()
    stego_array, _warnings = load_image(stego_png)

    pixel_tampered = stego_array.copy()
    pixel_tampered[40, 40, 0] ^= 0x80  # Keep the payload LSBs intact.
    pixel_tampered_png = save_png(pixel_tampered)
    pixel_checks = verify_pipeline(
        pixel_tampered_png,
        manifest,
        public_key,
        stego_passphrase=PASSWORD,
    )
    assert pixel_checks["checks"]["pixel_hash"]["ok"] is False
    assert pixel_checks["checks"]["manifest_signature"]["ok"] is True
    assert pixel_checks["checks"]["payload_signature"]["ok"] is True
    assert pixel_checks["overall_ok"] is False
    receiver_pixel_tamper = receiver_pipeline(
        pixel_tampered_png,
        PASSWORD,
        public_key,
        stego_passphrase=PASSWORD,
    )
    assert receiver_pixel_tamper.verified
    assert receiver_pixel_tamper.plaintext == "pipeline secret"

    manifest_tampered = dict(manifest)
    manifest_tampered["method"] = "lsb_match"
    changed_manifest = verify_pipeline(
        stego_png,
        manifest_tampered,
        public_key,
        stego_passphrase=PASSWORD,
    )
    assert changed_manifest["checks"]["pixel_hash"]["ok"] is True
    assert changed_manifest["checks"]["manifest_signature"]["ok"] is False
    assert changed_manifest["checks"]["payload_signature"]["ok"] is True
    assert changed_manifest["overall_ok"] is False

    payload_tampered = stego_array.copy()
    payload_tampered.reshape(-1)[0] ^= 1  # Corrupt keyed-mode salt.
    payload_result = receiver_pipeline(save_png(payload_tampered), PASSWORD, public_key)
    assert payload_result.stages[1].status == "failed"
    assert payload_result.payload is None
    assert payload_result.plaintext is None


def test_single_lsb_pixel_tamper_stops_before_packet_and_decrypt() -> None:
    """Flipping one embedded LSB invalidates extraction and cannot expose text."""
    stego_png, _manifest, _metrics, _diff, _warnings, public_key, _private_key = _send(
        message="single pixel tamper"
    )
    stego_array, _warnings = load_image(stego_png)
    stego_array = stego_array.copy()
    stego_array.reshape(-1)[0] ^= 1
    result = receiver_pipeline(
        save_png(stego_array),
        PASSWORD,
        public_key,
        stego_passphrase=PASSWORD,
    )
    assert result.stages[1].name == "extract_bits"
    assert result.stages[1].status == "failed"
    assert all(stage.status == "skipped" for stage in result.stages[2:])
    assert result.payload is None
    assert result.plaintext is None


@pytest.mark.parametrize("attack", ["jpeg", "resize"])
def test_lossy_or_resized_image_does_not_recover_plaintext(attack: str) -> None:
    """JPEG recompression and resizing invalidate the keyed embedded stream."""
    stego_png, _manifest, _metrics, _diff, _warnings, public_key, _private_key = _send()
    stego_array, _warnings = load_image(stego_png)
    if attack == "jpeg":
        image_buffer = BytesIO()
        Image.fromarray(stego_array).save(image_buffer, format="JPEG", quality=90)
        attacked_bytes = image_buffer.getvalue()
    else:
        image_buffer = BytesIO()
        Image.fromarray(stego_array).resize((48, 48), Image.Resampling.BILINEAR).save(
            image_buffer, format="PNG"
        )
        attacked_bytes = image_buffer.getvalue()

    result = receiver_pipeline(attacked_bytes, PASSWORD, public_key)
    assert not result.verified
    assert result.stages[1].name == "extract_bits"
    assert result.stages[1].status == "failed"
    assert result.payload is None
    assert result.plaintext is None


def test_cli_keygen_embed_extract_and_verify_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The documented module CLI completes keygen, embed, extract, and verify."""
    private_path = tmp_path / "sender-private.pem"
    public_path = tmp_path / "sender-public.pem"
    cover_path = tmp_path / "cover.png"
    stego_path = tmp_path / "stego.png"
    manifest_path = tmp_path / "manifest.json"
    cover_path.write_bytes(_cover_png())

    monkeypatch.setattr("app.cli.getpass.getpass", lambda _prompt: "KeyPassword123")
    assert (
        main(["keygen", "--private-key", str(private_path), "--public-key", str(public_path)]) == 0
    )
    capsys.readouterr()
    assert b"ENCRYPTED PRIVATE KEY" in private_path.read_bytes()

    prompt_values = iter((PASSWORD, "KeyPassword123"))
    monkeypatch.setattr("app.cli.getpass.getpass", lambda _prompt: next(prompt_values))
    assert (
        main(
            [
                "embed",
                "--cover",
                str(cover_path),
                "--message",
                "CLI secret",
                "--private-key",
                str(private_path),
                "--output",
                str(stego_path),
                "--manifest",
                str(manifest_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert stego_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["signature"]

    monkeypatch.setattr("app.cli.getpass.getpass", lambda _prompt: PASSWORD)
    assert (
        main(
            [
                "extract",
                "--image",
                str(stego_path),
                "--public-key",
                str(public_path),
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.strip() == "CLI secret"

    monkeypatch.setattr("app.cli.getpass.getpass", lambda _prompt: PASSWORD)
    assert (
        main(
            [
                "verify",
                "--image",
                str(stego_path),
                "--manifest",
                str(manifest_path),
                "--public-key",
                str(public_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["overall_ok"] is True


def test_cli_extract_failure_does_not_print_plaintext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A CLI wrong-password result reports failure but not message bytes."""
    stego_png, _manifest, _metrics, _diff, _warnings, _public_key, _private_key = _send(
        message="must not leak"
    )
    public_key = keys.generate_keypair()[1]
    public_path = tmp_path / "wrong-public.pem"
    public_path.write_text(keys.export_public_key_pem(public_key), encoding="utf-8")
    image_path = tmp_path / "stego.png"
    image_path.write_bytes(stego_png)

    monkeypatch.setattr("app.cli.getpass.getpass", lambda _prompt: PASSWORD)
    assert main(["extract", "--image", str(image_path), "--public-key", str(public_path)]) == 1
    captured = capsys.readouterr()
    assert "must not leak" not in captured.out
    assert "must not leak" not in captured.err
