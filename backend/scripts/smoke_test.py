"""End-to-end smoke test of a RUNNING StegaGuard site.

Run from ``backend/`` while the app is up (``scripts/start_app.ps1``)::

    python -m scripts.smoke_test                       # checks http://localhost:5173
    python -m scripts.smoke_test --url http://localhost:8080   # Docker

It drives the same requests the web pages make, through the UI's own origin (so the
proxy is tested too), and prints PASS/FAIL per check. Exit code 0 = everything works.
Use it right before a presentation. It uses throw-away keys and passwords, stores
nothing, and only reads the demo cover from ``frontend/public/demo``.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "smoke-test-password"
KEY_PASSWORD = "smoke-test-key-password"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str) -> Callable[[Callable[[], str]], Callable[[], str]]:
    """Register a check; an exception or failed assert is a FAIL with its message."""

    def wrap(function: Callable[[], str]) -> Callable[[], str]:
        started = time.perf_counter()
        try:
            detail = function()
            ok = True
        except Exception as error:  # noqa: BLE001 - report any failure, keep going
            detail, ok = f"{type(error).__name__}: {error}", False
        elapsed = (time.perf_counter() - started) * 1000
        RESULTS.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ({elapsed:.0f} ms)  {detail}", flush=True)
        return function

    return wrap


def cover_bytes() -> bytes:
    """Prefer an in-distribution BOSSbase demo cover, else any bundled demo image."""
    for name in ("bossbase_01.png", "cover.png"):
        path = ROOT / "frontend" / "public" / "demo" / name
        if path.is_file():
            return path.read_bytes()
    buffer = io.BytesIO()
    noise = np.random.default_rng(1).integers(0, 256, (256, 256), dtype=np.uint8)
    Image.fromarray(noise).save(buffer, format="PNG")
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    """Run all checks against the site."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:5173")
    args = parser.parse_args(argv)
    client = httpx.Client(base_url=args.url, timeout=60)
    state: dict[str, object] = {}

    @check("UI: home page and every route serve the app shell")
    def _() -> str:
        routes = [
            "/",
            "/hide",
            "/extract",
            "/detect",
            "/arms-race",
            "/tamper",
            "/batch",
            "/how-it-works",
            "/about",
        ]
        for route in routes:
            response = client.get(route)
            assert response.status_code == 200, f"{route} -> {response.status_code}"
            assert '<div id="root">' in response.text, f"{route} is not the app shell"
        return f"{len(routes)} routes"

    @check("UI: JS and CSS assets load")
    def _() -> str:
        html = client.get("/").text
        import re

        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
        assert assets, "no hashed assets referenced"
        for asset in assets:
            assert client.get(asset).status_code == 200, asset
        return f"{len(assets)} assets"

    @check("API via proxy: health and loaded models")
    def _() -> str:
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        return f"models: {', '.join(body['models_loaded']) or 'none (untrained)'}"

    @check("API: security headers present")
    def _() -> str:
        headers = client.get("/api/health").headers
        assert headers.get("x-content-type-options") == "nosniff"
        assert "default-src 'none'" in headers.get("content-security-policy", "")
        return "nosniff + CSP"

    @check("Keys: generate keypair (private key returned encrypted)")
    def _() -> str:
        body = client.post("/api/keys/generate", json={"key_password": KEY_PASSWORD}).json()
        assert "ENCRYPTED PRIVATE KEY" in body["private_key_pem_encrypted"]
        state["keys"] = body
        return f"fingerprint {body['fingerprint_short']}"

    @check("Hide: encrypt, sign, embed (returns exact PNG + signed manifest)")
    def _() -> str:
        keys = state["keys"]
        assert isinstance(keys, dict)
        message = "".join(chr(33 + (i * 7919 + 13) % 90) for i in range(1000))
        response = client.post(
            "/api/embed",
            data={
                "password": PASSWORD,
                "private_key_pem": keys["private_key_pem_encrypted"],
                "key_password": KEY_PASSWORD,
                "message": message,
            },
            files={"cover": ("cover.png", cover_bytes(), "image/png")},
        )
        assert response.status_code == 200, response.text[:200]
        body = response.json()
        state["stego"] = base64.b64decode(body["stego_png_base64"])
        state["manifest"] = body["manifest"]
        assert bytes(state["stego"]).startswith(b"\x89PNG")  # type: ignore[arg-type]
        return f"PSNR {body['metrics']['psnr']:.1f} dB, {body['metrics']['bpp']:.3f} bpp"

    @check("Extract: all 6 stages pass and the message comes back")
    def _() -> str:
        keys = state["keys"]
        assert isinstance(keys, dict)
        body = client.post(
            "/api/extract",
            data={"password": PASSWORD, "public_key_pem": keys["public_key_pem"]},
            files={"image": ("s.png", state["stego"], "image/png")},
        ).json()
        assert body["verified"] and body["plaintext"], body["stages"]
        assert [s["status"] for s in body["stages"]] == ["passed"] * 6
        return "verified, plaintext returned"

    @check("Extract: wrong password is rejected and returns NO plaintext")
    def _() -> str:
        keys = state["keys"]
        assert isinstance(keys, dict)
        body = client.post(
            "/api/extract",
            data={
                "password": "not-the-password",
                "public_key_pem": keys["public_key_pem"],
                "stego_passphrase": PASSWORD,
            },
            files={"image": ("s.png", state["stego"], "image/png")},
        ).json()
        assert not body["verified"] and body["plaintext"] is None
        failed = [s["name"] for s in body["stages"] if s["status"] == "failed"]
        return f"stopped at {failed[0]}"

    @check("2-LSB: hide, then Extract auto-detects the bit depth and verifies")
    def _() -> str:
        keys = state["keys"]
        assert isinstance(keys, dict)
        message = "".join(chr(33 + (i * 104729 + 7) % 90) for i in range(1500))
        embedded = client.post(
            "/api/embed",
            data={
                "password": PASSWORD,
                "private_key_pem": keys["private_key_pem_encrypted"],
                "key_password": KEY_PASSWORD,
                "message": message,
                "method": "lsb2_replace",
            },
            files={"cover": ("cover.png", cover_bytes(), "image/png")},
        ).json()
        stego2 = base64.b64decode(embedded["stego_png_base64"])
        body = client.post(
            "/api/extract",
            data={"password": PASSWORD, "public_key_pem": keys["public_key_pem"]},
            files={"image": ("s.png", stego2, "image/png")},
        ).json()
        assert body["verified"] and body["plaintext"] == message, body["stages"]
        assert body["technique"] == "lsb2", body["technique"]
        return f"{embedded['metrics']['bpp']:.3f} bpp, detected {body['technique']}"

    @check("Extract: the 1-bit image is reported as lsb and 2-LSB is not mistaken for it")
    def _() -> str:
        keys = state["keys"]
        assert isinstance(keys, dict)
        body = client.post(
            "/api/extract",
            data={"password": PASSWORD, "public_key_pem": keys["public_key_pem"]},
            files={"image": ("s.png", state["stego"], "image/png")},
        ).json()
        assert body["verified"] and body["technique"] == "lsb", body["technique"]
        forced = client.post(
            "/api/extract",
            data={
                "password": PASSWORD,
                "public_key_pem": keys["public_key_pem"],
                "technique": "lsb2",
            },
            files={"image": ("s.png", state["stego"], "image/png")},
        ).json()
        assert not forced["verified"] and forced["technique"] is None
        return "auto=lsb; forced lsb2 -> no hidden data"

    @check("Verify: manifest + pixel hash pass; one flipped pixel fails")
    def _() -> str:
        keys = state["keys"]
        assert isinstance(keys, dict)
        form = {
            "manifest": json.dumps(state["manifest"]),
            "public_key_pem": keys["public_key_pem"],
            "mode": "keyed",
            "stego_passphrase": PASSWORD,
        }
        good = client.post(
            "/api/verify", data=form, files={"image": ("s.png", state["stego"], "image/png")}
        ).json()
        assert good["overall_ok"], good
        pixels = np.asarray(Image.open(io.BytesIO(state["stego"])))  # type: ignore[arg-type]
        pixels = pixels.copy()
        pixels.reshape(-1)[-1] ^= 1
        buffer = io.BytesIO()
        Image.fromarray(pixels).save(buffer, format="PNG")
        bad = client.post(
            "/api/verify", data=form, files={"image": ("t.png", buffer.getvalue(), "image/png")}
        ).json()
        assert bad["checks"]["pixel_hash"]["ok"] is False
        return "intact passes, 1-pixel change fails the hash"

    @check("Detect: cover vs stego with every trained detector")
    def _() -> str:
        verdicts = []
        for name, image in (("cover", cover_bytes()), ("stego", state["stego"])):
            body = client.post(
                "/api/detect", files={"image": (f"{name}.png", image, "image/png")}
            ).json()
            detectors = {k: v for k, v in body["detectors"].items() if v.get("available")}
            verdicts.append(f"{name}={body['label']}({body['probability']:.2f})")
            assert detectors, "no detector available"
        return ", ".join(verdicts) + f" via {body['decision_source']}"

    @check("Detect: CNN heatmaps (Grad-CAM + residual) are returned when the CNN is loaded")
    def _() -> str:
        models = client.get("/api/models").json()
        if not models["detectors"]["cnn"]["trained"]:
            return "SKIPPED (CNN not trained)"
        body = client.post(
            "/api/detect", files={"image": ("s.png", state["stego"], "image/png")}
        ).json()
        assert body["heatmap_gradcam_png_base64"] and body["heatmap_residual_png_base64"]
        Image.open(io.BytesIO(base64.b64decode(body["heatmap_gradcam_png_base64"]))).verify()
        return "both heatmaps decode as images"

    @check("Batch: 3 images incl. one invalid file")
    def _() -> str:
        files = [
            ("images", ("a.png", cover_bytes(), "image/png")),
            ("images", ("b.png", b"not an image", "image/png")),
            ("images", ("c.png", state["stego"], "image/png")),
        ]
        items = client.post("/api/detect/batch", files=files).json()["items"]
        assert (
            items[0]["result"]
            and items[1]["error"]["code"] == "INVALID_IMAGE"
            and items[2]["result"]
        )
        return "per-file results and one per-file error"

    @check("Models endpoint lists detectors")
    def _() -> str:
        body = client.get("/api/models").json()
        assert set(body["detectors"]) == {"statistical", "rf", "cnn"}
        return ", ".join(
            f"{k}={'trained' if v['trained'] else 'untrained'}"
            for k, v in body["detectors"].items()
        )

    @check("Analytics: results/metrics.json served with every detector")
    def _() -> str:
        body = client.get("/api/results").json()
        assert body["conditions"], "no conditions"
        cnn = "cnn_v1" in body["detectors"]
        mismatch = bool(body.get("mismatch"))
        return f"{len(body['conditions'])} conditions; detectors {list(body['detectors'])}; CNN={cnn}; mismatch={mismatch}"

    @check("Analytics: saved plots are listed and served")
    def _() -> str:
        names = client.get("/api/results/plots").json()
        assert names, "no plots"
        response = client.get(f"/api/results/plots/{names[0]}")
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        return f"{len(names)} plots"

    @check("Errors: JPEG cover rejected for embedding with the uniform error envelope")
    def _() -> str:
        buffer = io.BytesIO()
        Image.fromarray(np.zeros((64, 64), np.uint8)).save(buffer, format="JPEG")
        keys = state["keys"]
        assert isinstance(keys, dict)
        response = client.post(
            "/api/embed",
            data={
                "password": PASSWORD,
                "private_key_pem": keys["private_key_pem_encrypted"],
                "key_password": KEY_PASSWORD,
                "message": "x",
            },
            files={"cover": ("c.jpg", buffer.getvalue(), "image/jpeg")},
        )
        assert (
            response.status_code == 415 and response.json()["error"]["code"] == "UNSUPPORTED_FORMAT"
        )
        return "415 UNSUPPORTED_FORMAT"

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED:", *failed, sep="\n  - ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
