"""End-to-end API tests with FastAPI's TestClient (everything stays in memory)."""

import base64
import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.limits import rate_limiter
from app.config import BACKEND_DIR, settings
from app.main import app

pytestmark = pytest.mark.integration


def stc_installed() -> bool:
    """True when the compiled pySTC extension can be imported (it needs a C++ compiler to build)."""
    try:
        from pystc import pystc  # noqa: F401
    except ImportError:
        return False
    return True


MESSAGE_PASSWORD = "correct horse battery"
KEY_PASSWORD = "key-password-123"
SECRET_TEXT = "meet at the old bridge at nine"


def png_bytes(array: np.ndarray, image_format: str = "PNG") -> bytes:
    """Encode an array as an image file in memory."""
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format=image_format)
    return buffer.getvalue()


def noise_image(height: int = 128, width: int = 128, channels: int = 1, seed: int = 3) -> bytes:
    """A small random cover; content does not matter for crypto/stego round trips."""
    rng = np.random.default_rng(seed)
    shape = (height, width) if channels == 1 else (height, width, channels)
    return png_bytes(rng.integers(0, 256, shape, dtype=np.uint8))


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Client with no trained models and empty results, and a fresh rate limiter."""
    monkeypatch.setattr(settings, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(settings, "RESULTS_DIR", tmp_path / "results")
    rate_limiter.reset()
    monkeypatch.setattr(rate_limiter, "limit", 10_000)
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def keypair() -> dict[str, str]:
    """One generated keypair shared by the module (key generation is slowish)."""
    rate_limiter.reset()
    with TestClient(app) as client:
        response = client.post("/api/keys/generate", json={"key_password": KEY_PASSWORD})
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


def embed(
    client: TestClient,
    keys: dict[str, str],
    cover: bytes | None = None,
    **fields: Any,
) -> Any:
    """POST /embed with sensible defaults, returning the raw response."""
    data = {
        "password": MESSAGE_PASSWORD,
        "private_key_pem": keys["private_key_pem_encrypted"],
        "key_password": KEY_PASSWORD,
        "message": SECRET_TEXT,
        **fields,
    }
    files = {"cover": ("cover.png", cover or noise_image(), "image/png")}
    return client.post("/api/embed", data=data, files=files)


def extract(client: TestClient, image: bytes, public_key: str, **fields: Any) -> Any:
    """POST /extract with defaults."""
    data = {"password": MESSAGE_PASSWORD, "public_key_pem": public_key, **fields}
    return client.post("/api/extract", data=data, files={"image": ("s.png", image, "image/png")})


def error_code(response: Any) -> str:
    """Return the code from the uniform error envelope."""
    return str(response.json()["error"]["code"])


# --- keys -----------------------------------------------------------------


def test_generate_keys_returns_encrypted_private_key(keypair: dict[str, str]) -> None:
    """The private key is exported only in encrypted PKCS#8 form."""
    assert "ENCRYPTED PRIVATE KEY" in keypair["private_key_pem_encrypted"]
    assert keypair["public_key_pem"].startswith("-----BEGIN PUBLIC KEY-----")
    # Display format: 64 hex characters in groups of four (Section 6.5).
    hex_digits = keypair["fingerprint"].replace(" ", "")
    assert len(hex_digits) == 64
    assert hex_digits.startswith(keypair["fingerprint_short"])


def test_weak_key_password_is_rejected(api: TestClient) -> None:
    """Section 6.4 minimum password length applies to key passwords too."""
    response = api.post("/api/keys/generate", json={"key_password": "short"})
    assert response.status_code == 422
    assert error_code(response) == "WEAK_PASSWORD"


# --- embed / extract ------------------------------------------------------


def test_embed_then_extract_round_trip(api: TestClient, keypair: dict[str, str]) -> None:
    """Happy path: the message comes back only after every stage passes."""
    response = embed(api, keypair)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["metrics"]["psnr"] > 50
    # The manifest stores plain hex; the key endpoint returns the grouped display form.
    assert body["manifest"]["sender_fingerprint"] == keypair["fingerprint"].replace(" ", "")
    stego = base64.b64decode(body["stego_png_base64"])
    assert stego.startswith(b"\x89PNG")

    result = extract(api, stego, keypair["public_key_pem"]).json()
    assert result["verified"] is True
    assert result["plaintext"] == SECRET_TEXT
    assert [stage["status"] for stage in result["stages"]] == ["passed"] * 6


def test_file_payload_round_trip_sanitizes_filename(
    api: TestClient, keypair: dict[str, str]
) -> None:
    """Files are returned as base64 with a safe filename."""
    payload = bytes(range(200))
    response = api.post(
        "/api/embed",
        data={
            "password": MESSAGE_PASSWORD,
            "private_key_pem": keypair["private_key_pem_encrypted"],
            "key_password": KEY_PASSWORD,
            "mode": "sequential",
        },
        files={
            "cover": ("cover.png", noise_image(), "image/png"),
            "message_file": ("../../evil<name>.bin", payload, "application/octet-stream"),
        },
    )
    assert response.status_code == 200, response.text
    stego = base64.b64decode(response.json()["stego_png_base64"])
    result = extract(api, stego, keypair["public_key_pem"], mode="sequential").json()
    assert result["verified"] is True
    assert base64.b64decode(result["file_base64"]) == payload
    assert result["filename"] == "evil_name_.bin"


@pytest.fixture(scope="module")
def stego_sample(keypair: dict[str, str]) -> dict[str, Any]:
    """One keyed stego image and its manifest, reused by tamper tests."""
    rate_limiter.reset()
    with TestClient(app) as client:
        body = embed(client, keypair).json()
    return {"png": base64.b64decode(body["stego_png_base64"]), "manifest": body["manifest"]}


def failed_stage(result: dict[str, Any]) -> tuple[str, str]:
    """Return (name, code) of the failed stage and check later stages were skipped."""
    statuses = [stage["status"] for stage in result["stages"]]
    index = statuses.index("failed")
    assert all(status == "skipped" for status in statuses[index + 1 :])
    stage = result["stages"][index]
    return stage["name"], stage["code"]


def test_wrong_password_never_returns_plaintext(
    api: TestClient, keypair: dict[str, str], stego_sample: dict[str, Any]
) -> None:
    """Signature passes, decryption fails, and no content is returned."""
    response = extract(
        api,
        stego_sample["png"],
        keypair["public_key_pem"],
        password="not the password",
        stego_passphrase=MESSAGE_PASSWORD,
    )
    result = response.json()
    assert result["verified"] is False
    assert failed_stage(result) == ("derive_key_and_decrypt", "DECRYPTION_FAILED")
    assert result["plaintext"] is None and result["file_base64"] is None
    assert SECRET_TEXT not in response.text


def test_wrong_public_key_reports_key_mismatch(
    api: TestClient, stego_sample: dict[str, Any]
) -> None:
    """A different sender key stops before signature verification and decryption."""
    other = api.post("/api/keys/generate", json={"key_password": KEY_PASSWORD}).json()
    result = extract(api, stego_sample["png"], other["public_key_pem"]).json()
    assert failed_stage(result) == ("check_sender", "KEY_MISMATCH")


def test_wrong_stego_passphrase_looks_like_no_hidden_data(
    api: TestClient, keypair: dict[str, str], stego_sample: dict[str, Any]
) -> None:
    """Wrong key and no data are indistinguishable (Section 5.2 rule 9)."""
    wrong = extract(
        api, stego_sample["png"], keypair["public_key_pem"], stego_passphrase="wrong passphrase"
    ).json()
    clean = extract(api, noise_image(seed=99), keypair["public_key_pem"]).json()
    assert failed_stage(wrong) == ("extract_bits", "NO_HIDDEN_DATA")
    assert failed_stage(clean) == ("extract_bits", "NO_HIDDEN_DATA")
    assert wrong["stages"][1]["detail"] == clean["stages"][1]["detail"]


def test_jpeg_resave_destroys_payload(
    api: TestClient, keypair: dict[str, str], stego_sample: dict[str, Any]
) -> None:
    """Lossy re-encoding rewrites LSBs, so nothing can be extracted."""
    pixels = np.asarray(Image.open(io.BytesIO(stego_sample["png"])))
    result = extract(api, png_bytes(pixels, "JPEG"), keypair["public_key_pem"]).json()
    assert result["verified"] is False
    assert failed_stage(result)[1] in {"NO_HIDDEN_DATA", "VERIFICATION_FAILED"}


# --- verify ---------------------------------------------------------------


def verify(client: TestClient, image: bytes, manifest: Any, public_key: str, **fields: Any) -> Any:
    """POST /verify."""
    text = manifest if isinstance(manifest, str) else json.dumps(manifest)
    return client.post(
        "/api/verify",
        data={"manifest": text, "public_key_pem": public_key, **fields},
        files={"image": ("s.png", image, "image/png")},
    )


def test_verify_all_three_checks_pass(
    api: TestClient, keypair: dict[str, str], stego_sample: dict[str, Any]
) -> None:
    """Untouched image + manifest + payload all verify."""
    body = verify(
        api,
        stego_sample["png"],
        stego_sample["manifest"],
        keypair["public_key_pem"],
        mode="keyed",
        stego_passphrase=MESSAGE_PASSWORD,
    ).json()
    assert body["overall_ok"] is True
    assert all(check["ok"] for check in body["checks"].values())


def test_one_flipped_pixel_fails_pixel_hash(
    api: TestClient, keypair: dict[str, str], stego_sample: dict[str, Any]
) -> None:
    """Changing a single LSB anywhere breaks check A."""
    pixels = np.asarray(Image.open(io.BytesIO(stego_sample["png"]))).copy()
    pixels[-1, -1] ^= 1
    body = verify(
        api, png_bytes(pixels), stego_sample["manifest"], keypair["public_key_pem"]
    ).json()
    assert body["checks"]["pixel_hash"]["ok"] is False
    assert body["checks"]["manifest_signature"]["ok"] is True
    assert body["checks"]["payload_signature"] is None
    assert body["overall_ok"] is False


def test_edited_manifest_fails_signature(
    api: TestClient, keypair: dict[str, str], stego_sample: dict[str, Any]
) -> None:
    """Changing any manifest field invalidates its signature (check B)."""
    manifest = {**stego_sample["manifest"], "payload_bytes": 1}
    body = verify(api, stego_sample["png"], manifest, keypair["public_key_pem"]).json()
    assert body["checks"]["manifest_signature"]["ok"] is False
    assert body["overall_ok"] is False


def test_verify_rejects_malformed_manifest(
    api: TestClient, keypair: dict[str, str], stego_sample: dict[str, Any]
) -> None:
    """Non-JSON manifests are a client error."""
    response = verify(api, stego_sample["png"], "{not json", keypair["public_key_pem"])
    assert response.status_code == 400
    assert error_code(response) == "BAD_REQUEST"


# --- input validation and error codes -------------------------------------


def test_jpeg_cover_is_rejected_for_embedding(api: TestClient, keypair: dict[str, str]) -> None:
    """JPEG covers would destroy the payload, so embedding refuses them."""
    rng = np.random.default_rng(0)
    jpeg = png_bytes(rng.integers(0, 256, (64, 64), dtype=np.uint8), "JPEG")
    response = embed(api, keypair, cover=jpeg)
    assert response.status_code == 415
    assert error_code(response) == "UNSUPPORTED_FORMAT"


def test_capacity_exceeded_reports_maximum(api: TestClient, keypair: dict[str, str]) -> None:
    """Too-long messages fail with the maximum size in the details."""
    response = embed(api, keypair, cover=noise_image(32, 32), message="x" * 5000)
    assert response.status_code == 422
    assert error_code(response) == "CAPACITY_EXCEEDED"
    assert response.json()["error"]["details"]["maximum_payload_bytes"] > 0


def test_weak_message_password(api: TestClient, keypair: dict[str, str]) -> None:
    """Passwords shorter than eight characters are refused."""
    response = embed(api, keypair, password="short")
    assert error_code(response) == "WEAK_PASSWORD"


def test_wrong_key_password_is_bad_key(api: TestClient, keypair: dict[str, str]) -> None:
    """A private key that cannot be unlocked is BAD_KEY."""
    response = embed(api, keypair, key_password="wrong-key-password")
    assert response.status_code == 400
    assert error_code(response) == "BAD_KEY"


def test_malformed_public_key_is_bad_key(api: TestClient) -> None:
    """Garbage PEM text is BAD_KEY."""
    response = extract(api, noise_image(), "not a pem")
    assert error_code(response) == "BAD_KEY"


def test_non_image_upload_is_invalid(api: TestClient, keypair: dict[str, str]) -> None:
    """Uploads are validated by decoding, not by extension."""
    response = embed(api, keypair, cover=b"definitely not an image")
    assert response.status_code == 400
    assert error_code(response) == "INVALID_IMAGE"


def test_too_many_pixels_for_embedding(api: TestClient, keypair: dict[str, str]) -> None:
    """A 5-megapixel cover exceeds the 4 MP embed limit before decoding."""
    big = png_bytes(np.zeros((2000, 2500), dtype=np.uint8))
    response = embed(api, keypair, cover=big)
    assert response.status_code == 413
    assert error_code(response) == "IMAGE_TOO_LARGE"


def test_decompression_bomb_is_rejected(api: TestClient) -> None:
    """A tiny file declaring 25 megapixels is refused from its header alone."""
    bomb = png_bytes(np.zeros((5000, 5000), dtype=np.uint8))
    assert len(bomb) < settings.MAX_UPLOAD_SIZE_BYTES
    response = api.post("/api/detect", files={"image": ("bomb.png", bomb, "image/png")})
    assert response.status_code == 413
    assert error_code(response) == "IMAGE_TOO_LARGE"


def test_oversized_upload_is_rejected(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bodies over the size cap are refused before parsing."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 10_000)
    payload = b"\x00" * 600_000
    response = api.post("/api/detect", files={"image": ("big.png", payload, "image/png")})
    assert response.status_code == 413
    assert error_code(response) == "IMAGE_TOO_LARGE"


def test_validation_errors_do_not_echo_secrets(api: TestClient) -> None:
    """Missing fields are reported by name only, never with submitted values."""
    response = api.post("/api/embed", data={"password": "super-secret-value"})
    assert response.status_code == 400
    assert "super-secret-value" not in response.text


def test_rate_limit_returns_retry_after(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST endpoints are limited per client and say when to retry."""
    monkeypatch.setattr(rate_limiter, "limit", 2)
    rate_limiter.reset()
    for _ in range(2):
        api.post("/api/keys/generate", json={"key_password": "short"})
    response = api.post("/api/keys/generate", json={"key_password": "short"})
    assert response.status_code == 429
    assert error_code(response) == "RATE_LIMITED"
    assert int(response.headers["Retry-After"]) >= 1


# --- detect ---------------------------------------------------------------


def test_detect_without_trained_models_is_honest(api: TestClient) -> None:
    """With no models, only the untrained statistical detector decides."""
    response = api.post("/api/detect", files={"image": ("i.png", noise_image(), "image/png")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision_source"] == "statistical (untrained)"
    assert body["detectors"]["rf"]["available"] is False
    assert body["detectors"]["cnn"]["available"] is False
    assert any("No trained detector" in warning for warning in body["warnings"])
    assert body["label"] in {"clean", "suspected_stego"}
    assert len(body["image_sha256"]) == 64


def test_detect_with_real_classical_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The committed HGB model loads and scores an image."""
    if not (BACKEND_DIR / "models" / "classical_hgb.joblib").is_file():
        pytest.skip("classical_hgb model not present")
    monkeypatch.setattr(settings, "MODELS_DIR", BACKEND_DIR / "models")
    rate_limiter.reset()
    with TestClient(app) as client:
        body = client.post(
            "/api/detect",
            data={"detectors": "statistical,rf"},
            files={"image": ("i.png", noise_image(), "image/png")},
        ).json()
        models = client.get("/api/models").json()
    assert body["detectors"]["rf"]["available"] is True
    assert body["detectors"]["rf"]["model"] in {"classical_rf", "classical_hgb"}
    assert 0.0 <= body["probability"] <= 1.0
    assert models["detectors"]["rf"]["trained"] is True
    assert all("feature_names" not in m["metadata"] for m in models["models"])


def test_detect_rejects_unknown_detector(api: TestClient) -> None:
    """Only statistical, rf, and cnn are valid detector names."""
    response = api.post(
        "/api/detect",
        data={"detectors": "magic"},
        files={"image": ("i.png", noise_image(), "image/png")},
    )
    assert error_code(response) == "BAD_REQUEST"


def test_jpeg_detection_is_allowed_with_warning(api: TestClient) -> None:
    """JPEG may be scanned, but the response warns that results mean less."""
    rng = np.random.default_rng(1)
    jpeg = png_bytes(rng.integers(0, 256, (64, 64), dtype=np.uint8), "JPEG")
    body = api.post("/api/detect", files={"image": ("i.jpg", jpeg, "image/jpeg")}).json()
    assert any("JPEG" in warning for warning in body["warnings"])


def test_batch_detect_reports_per_file_errors(api: TestClient) -> None:
    """One undecodable file does not fail the whole batch."""
    files = [
        ("images", ("a.png", noise_image(seed=1), "image/png")),
        ("images", ("b.png", b"garbage", "image/png")),
        ("images", ("c.png", noise_image(64, 64, 3, seed=2), "image/png")),
    ]
    items = api.post("/api/detect/batch", files=files).json()["items"]
    assert [item["filename"] for item in items] == ["a.png", "b.png", "c.png"]
    assert items[0]["result"] is not None
    assert items[1]["error"]["code"] == "INVALID_IMAGE"
    assert items[2]["result"]["channels"] == 3


# --- results and models ---------------------------------------------------


def test_results_unavailable_until_evaluation_runs(api: TestClient) -> None:
    """No metrics file means no numbers — never placeholders."""
    response = api.get("/api/results")
    assert response.status_code == 503
    assert error_code(response) == "MODEL_UNAVAILABLE"


def test_results_and_plots_are_served_from_disk(api: TestClient, tmp_path: Path) -> None:
    """metrics.json is returned verbatim and plot names cannot escape the folder."""
    results = tmp_path / "results"
    (results / "plots").mkdir(parents=True)
    (results / "metrics.json").write_text('{"format_version": 1}', encoding="utf-8")
    (results / "plots" / "roc_curve.png").write_bytes(png_bytes(np.zeros((4, 4), np.uint8)))
    assert api.get("/api/results").json() == {"format_version": 1}
    assert api.get("/api/results/plots").json() == ["roc_curve.png"]
    assert api.get("/api/results/plots/roc_curve.png").status_code == 200
    assert api.get("/api/results/plots/..%2Fmetrics.json").status_code == 404
    assert api.get("/api/results/plots/missing.png").status_code == 404


def test_security_headers_present(api: TestClient) -> None:
    """Every API response carries the defensive headers."""
    response = api.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert response.headers["Cache-Control"] == "no-store"


# --- log hygiene ----------------------------------------------------------


def test_logs_never_contain_secrets(
    api: TestClient, keypair: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    """Passwords, plaintext, and PEM material never reach any logger."""
    caplog.set_level(logging.DEBUG)
    body = embed(api, keypair).json()
    stego = base64.b64decode(body["stego_png_base64"])
    extract(api, stego, keypair["public_key_pem"])
    extract(api, stego, keypair["public_key_pem"], password="wrong password!")
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "/api/embed" in logged  # the access log did run
    for secret in (
        MESSAGE_PASSWORD,
        KEY_PASSWORD,
        SECRET_TEXT,
        "BEGIN",
        keypair["private_key_pem_encrypted"][40:80],
    ):
        assert secret not in logged


# --- 2-LSB and technique auto-detection -----------------------------------


def test_2lsb_embed_extract_reports_detected_technique(
    api: TestClient, keypair: dict[str, str]
) -> None:
    """2-LSB hides twice as much, and Extract auto-detects the bit depth."""
    response = embed(api, keypair, method="lsb2_replace")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["metrics"]["capacity_bits"] > 2 * (128 * 128 - 128) - 1  # two bits per sample
    stego = base64.b64decode(body["stego_png_base64"])

    result = extract(api, stego, keypair["public_key_pem"]).json()
    assert result["verified"] is True and result["plaintext"] == SECRET_TEXT
    assert result["technique"] == "lsb2"
    assert "2-bit" in result["stages"][1]["detail"]

    forced = extract(api, stego, keypair["public_key_pem"], technique="lsb2").json()
    assert forced["verified"] is True and forced["technique"] == "lsb2"


def test_1bit_stego_is_reported_as_lsb_and_wrong_forced_technique_fails(
    api: TestClient, keypair: dict[str, str]
) -> None:
    """Auto finds 1-bit LSB; forcing 2-LSB on it looks exactly like 'no hidden data'."""
    stego = base64.b64decode(embed(api, keypair).json()["stego_png_base64"])
    assert extract(api, stego, keypair["public_key_pem"]).json()["technique"] == "lsb"
    forced = extract(api, stego, keypair["public_key_pem"], technique="lsb2").json()
    assert forced["verified"] is False and forced["technique"] is None
    assert failed_stage(forced) == ("extract_bits", "NO_HIDDEN_DATA")


@pytest.mark.skipif(not stc_installed(), reason="pystcstego is not installed")
@pytest.mark.parametrize("method", ["suniward", "hill"])
def test_adaptive_stc_api_round_trip(method: str, api: TestClient, keypair: dict[str, str]) -> None:
    """Both adaptive methods carry a signed message through the public API and auto decoder."""
    embedded = embed(api, keypair, method=method)
    assert embedded.status_code == 200, embedded.text
    stego = base64.b64decode(embedded.json()["stego_png_base64"])
    recovered = extract(api, stego, keypair["public_key_pem"], technique="auto").json()
    assert recovered["verified"] is True
    assert recovered["plaintext"] == SECRET_TEXT
    assert recovered["technique"] == "stc"


def test_2lsb_fits_a_message_that_one_bit_lsb_cannot(
    api: TestClient, keypair: dict[str, str]
) -> None:
    """On a 64x64 cover, 700 bytes need 2-LSB; 1-bit LSB reports the capacity limit."""
    cover = noise_image(64, 64)
    assert error_code(embed(api, keypair, cover=cover, message="y" * 400)) == "CAPACITY_EXCEEDED"
    assert (
        embed(api, keypair, cover=cover, message="y" * 400, method="lsb2_replace").status_code
        == 200
    )


def test_verify_accepts_technique_for_the_payload_check(
    api: TestClient, keypair: dict[str, str]
) -> None:
    """Check C (embedded signature) works for a 2-LSB image with technique auto."""
    body = embed(api, keypair, method="lsb2_replace").json()
    stego = base64.b64decode(body["stego_png_base64"])
    result = verify(
        api,
        stego,
        body["manifest"],
        keypair["public_key_pem"],
        mode="keyed",
        stego_passphrase=MESSAGE_PASSWORD,
    ).json()
    assert result["overall_ok"] is True
    assert result["checks"]["payload_signature"]["ok"] is True


def test_invalid_technique_is_a_bad_request(api: TestClient, keypair: dict[str, str]) -> None:
    """Unknown decoder choices are rejected."""
    response = extract(api, noise_image(), keypair["public_key_pem"], technique="lsb3")
    assert response.status_code == 400 and error_code(response) == "BAD_REQUEST"


# --- placement-mode auto-detection ---------------------------------------


@pytest.mark.parametrize("mode", ["keyed", "sequential"])
def test_extract_auto_mode_finds_either_placement(
    api: TestClient, keypair: dict[str, str], mode: str
) -> None:
    stego = embed(api, keypair, mode=mode).json()["stego_png_base64"]
    result = extract(api, base64.b64decode(stego), keypair["public_key_pem"]).json()
    assert result["verified"] is True
    assert result["mode"] == mode
    assert result["plaintext"] == SECRET_TEXT


def test_extract_auto_mode_wrong_password_reveals_nothing(
    api: TestClient, keypair: dict[str, str]
) -> None:
    stego = embed(api, keypair, mode="keyed").json()["stego_png_base64"]
    result = extract(
        api, base64.b64decode(stego), keypair["public_key_pem"], password="wrong-password"
    ).json()
    assert result["verified"] is False
    assert result["plaintext"] is None
    assert result["mode"] is None
