# StegaGuard — AI-Based Image Steganalysis with Cryptographic Verification for Covert Communication

> **Master blueprint for an AI coding agent (Google Antigravity, GitHub Copilot Agent mode, or any IDE agent).**
> Read this entire file first. Then build the project **one phase at a time**, stopping after each phase for review.
> Project title (fixed, do not change): **AI-Based Image Steganalysis with Cryptographic Verification for Covert Communication**.
> Working name of the codebase: **StegaGuard**.
> Context: academic project for the ISC subject (Information Security & Cryptography), delivered as working code, a website, and a live demo. Last updated 2026-11-14.

---

## 0. How the agent must work (operating protocol)

1. **Read this whole file before writing any code.** Do not skim.
2. **Work phase by phase** (Section 9). Never start phase N+1 until phase N's acceptance criteria pass.
3. **At the start of each phase:** produce a short implementation plan (files to create, functions, tests) and wait for the user's approval if your IDE supports plan review.
4. **At the end of each phase:** run the tests and linters, then print a short report: what was built, test results, anything deferred, and the exact command to run it. Then **STOP** and wait for the user to say "continue".
5. **Decisions in Section 2 are already made.** Do not ask the user to re-decide them. Ask a question only if you are truly blocked.
6. **Never invent results.** Every number shown in the UI, README or docs must come from a real script run saved in `backend/results/`. If a model is not trained yet, say so in the UI instead of showing fake numbers.
7. **Explainability is a requirement.** The student must explain every function in a viva. Write clear docstrings, short functions, and comments that explain *why* (especially in crypto and steganalysis code). Avoid clever one-liners.
8. **Security rules are non-negotiable** (Section 5). If a request or shortcut would break them, do not take it.
9. Prefer small commits with clear messages (one logical change each). Do not commit datasets, trained weights over 50 MB, `.env` files, or any key material.
10. If something in this blueprint is wrong or impossible (for example a library API changed), choose the closest correct alternative, note it in `docs/DECISIONS.md`, and continue.

**If time is short, the minimum viable path is:** Phases 0 → 1 → 2 → 3 → 5 → 8 → 9, then add Phase 6 (CNN) if a GPU or Google Colab is available. Phases 10–13 are what make the project "advanced".

---

## 1. Project overview

### 1.1 One-paragraph description
StegaGuard is a full-stack system that covers both sides of covert communication on images. The **sender** encrypts a secret message with AES-256-GCM, signs it with Ed25519, and hides the signed ciphertext inside a lossless image using least-significant-bit (LSB) steganography. The **receiver** extracts the hidden data and **verifies the signature and integrity before decrypting anything**. The **defender (steganalysis side)** scans any image with classical statistical attacks (chi-square, RS analysis, Sample Pair Analysis) and a deep-learning detector (CNN with a fixed high-pass first layer), and reports whether the image likely hides data, with a confidence score and an explanation heatmap. A web dashboard demonstrates the whole "arms race".

### 1.2 The three parts of the title map to three subsystems

| Title phrase | Subsystem | What it does |
|---|---|---|
| Covert Communication | **Stego engine** | LSB replacement and LSB matching embedding, keyed pseudo-random scatter, payload packaging |
| Cryptographic Verification | **Crypto engine** | Argon2id key derivation, AES-256-GCM, Ed25519 signatures, signed integrity manifest, verify-before-decrypt |
| AI-Based Image Steganalysis | **Detection engine** | Classical attacks + trained Random Forest + CNN + calibrated ensemble + heatmaps |

### 1.3 Goals
- G1. A message hidden in an image can be recovered byte-for-byte by the right receiver, and **only** if the signature verifies.
- G2. Any tampering with the stego image or manifest is detected and reported with a reason.
- G3. The detector reliably flags LSB-replacement stego at moderate/high payloads and honestly reports where it struggles (low payload, LSB matching).
- G4. A polished, advanced website lets anyone try every part live and shows the evaluation results.
- G5. Everything is reproducible: one command per stage, fixed seeds, saved metrics, tests, Docker.

### 1.4 Non-goals (say so in the docs)
- Not a production-grade secure messenger. Python cannot guarantee memory zeroization, and LSB stego does not survive JPEG compression or resizing.
- Not defeating state-of-the-art content-adaptive steganography (HUGO, WOW, S-UNIWARD). These are mentioned as future work.
- Educational use only. Use on your own images. See `docs/ETHICS.md`.

---

## 2. Decisions already made (do not re-ask)

| Topic | Decision |
|---|---|
| Language/backend | Python 3.11+ with FastAPI, Pydantic v2 |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS + React Router + TanStack Query + Recharts + Framer Motion |
| Deep learning | PyTorch; training on Google Colab GPU (or local GPU); CPU-only inference in the app |
| Classical ML | scikit-learn (Random Forest primary, HistGradientBoosting secondary) |
| Crypto library | `cryptography` (AES-GCM, Ed25519, HKDF, ChaCha20, Scrypt fallback) + `argon2-cffi` (Argon2id) |
| Image format for stego | **Lossless only**: PNG (primary), BMP/PGM accepted as input. JPEG rejected for embedding with a clear explanation. Output always PNG with metadata stripped |
| Pixel domain | 8-bit. Grayscale ("L") and RGB supported. RGBA/palette inputs are converted to RGB with a visible warning |
| Embedding methods | `lsb_replace` (core), `lsb_match` (±1, stealthier, advanced) |
| Embedding modes | `keyed` (default: keyed pseudo-random scatter + whitening) and `sequential` (educational: plain raster order) |
| Bits per sample | 1 LSB per sample in the core. 2 LSBs is a stretch goal |
| Payload unit | **bits per pixel (bpp)** of the cover image (not "percent") — standard in the literature |
| Evaluation payloads | 0.05, 0.1, 0.2, 0.4, 1.0 bpp |
| Dataset | BOSSbase 1.01 (10,000 grayscale 512×512 images) resized to 256×256; fallback described in Phase 4 |
| CNN input | single channel, 256×256 crop; RGB images scored per channel and aggregated; large images scored by tiling |
| Augmentation | Only flips and 90° rotations. **Never** resize, JPEG, blur, or brighten (these destroy the stego signal) |
| Signature scheme | Ed25519 (sender keypair). Optional HMAC-SHA256 mode as a stretch goal |
| Secrets handling | Server is stateless: it never stores keys, passwords, images or messages |
| Deployment | Docker + docker-compose; CI with GitHub Actions |

---

## 3. System architecture

### 3.1 High-level diagram

```mermaid
flowchart LR
  subgraph Sender
    M[Secret message/file] --> E[AES-256-GCM encrypt<br/>key = Argon2id(password, salt)]
    E --> S[Ed25519 sign packet]
    S --> P[Packet bytes]
    C[Cover image PNG] --> EMB
    P --> EMB[Stego embed<br/>lsb_replace / lsb_match<br/>keyed or sequential]
    EMB --> SI[Stego PNG]
    EMB --> MAN[Signed manifest JSON<br/>pixel SHA-256 + metadata]
  end
  subgraph Receiver
    SI2[Stego PNG] --> X[Extract bits]
    X --> V{Verify Ed25519 signature<br/>+ manifest hash}
    V -- fail --> R1[Reject. Never decrypt]
    V -- pass --> D[AES-GCM decrypt]
    D --> OUT[Plaintext]
  end
  subgraph Defender
    ANY[Any image] --> CL[Classical attacks<br/>chi-square, RS, SPA, features]
    ANY --> CNN[CNN steganalyzer<br/>tiles + Grad-CAM]
    CL --> ENS[Calibrated ensemble]
    CNN --> ENS
    ENS --> RES[Clean / Stego + confidence + heatmap]
  end
  SI --> SI2
  SI --> ANY
```

### 3.2 Layering rule
`core/` (pure functions, no web framework) → `steganalysis/` (pure functions + model loading) → `api/` (thin HTTP layer) → `frontend/`. Core modules must never import FastAPI. This keeps unit tests fast and explanations simple.

---

## 4. Repository layout (create exactly this)

```
stegaguard/
├── AGENTS.md                         # rules for AI agents (template in Appendix A)
├── .github/
│   ├── copilot-instructions.md       # copy of AGENTS.md for Copilot
│   └── workflows/ci.yml
├── PROJECT_BLUEPRINT.md              # this file
├── README.md
├── Makefile                          # make setup | test | lint | dataset | train | eval | run | docker
├── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md  THREAT_MODEL.md  MODEL_CARD.md  API.md
│   ├── DECISIONS.md     ETHICS.md        DEMO_SCRIPT.md  VIVA_QA.md
├── backend/
│   ├── pyproject.toml                # ruff, mypy, pytest config
│   ├── requirements.txt  requirements-dev.txt  requirements-train.txt
│   ├── app/
│   │   ├── main.py  config.py
│   │   ├── api/        routes_keys.py routes_embed.py routes_extract.py routes_verify.py
│   │   │               routes_detect.py routes_models.py routes_results.py
│   │   │               schemas.py errors.py deps.py limits.py
│   │   ├── core/
│   │   │   ├── crypto/ kdf.py aead.py signing.py keys.py packet.py manifest.py
│   │   │   ├── stego/  image_io.py bitops.py keystream.py scatter.py header.py
│   │   │   │           lsb_replace.py lsb_match.py embed.py extract.py metrics.py
│   │   │   ├── analysis/ bitplane.py diffmap.py
│   │   │   └── pipeline.py           # sender_pipeline(), receiver_pipeline()
│   │   ├── steganalysis/
│   │   │   ├── classical/ chi_square.py rs.py spa.py features.py rf_model.py
│   │   │   ├── deep/      filters.py model.py dataset.py train.py gradcam.py infer.py
│   │   │   ├── tiling.py  ensemble.py  registry.py  calibration.py
│   │   └── utils/ logging.py hashing.py
│   ├── scripts/ prepare_dataset.py train_classical.py train_cnn.py evaluate.py make_demo_assets.py
│   ├── tests/   unit/ integration/ fixtures/
│   ├── models/  (weights gitignored; model_card.json tracked)
│   ├── results/ (metrics.json, plots; tracked, small)
│   └── data/    (gitignored)
├── frontend/
│   ├── package.json  vite.config.ts  tailwind.config.ts  tsconfig.json
│   └── src/
│       ├── main.tsx App.tsx routes.tsx
│       ├── api/ client.ts types.ts hooks.ts
│       ├── components/ ui/ ImageDropzone ConfidenceGauge HeatmapOverlay BitPlaneViewer
│       │               DiffViewer VerificationTimeline MetricCard RocChart ConfusionMatrix
│       │               SecretInput FileCard Stepper EmptyState ErrorBanner
│       ├── pages/  Home Hide ExtractVerify Detect ArmsRace TamperLab BatchScan Analytics HowItWorks About
│       ├── lib/    bitplane.ts canvas.ts format.ts download.ts
│       └── styles/ index.css
└── notebooks/colab_train_cnn.ipynb   # thin wrapper that calls scripts/train_cnn.py
```

---

## 5. Global engineering and security rules

### 5.1 Code quality
- Python: type hints everywhere, `ruff` + `mypy --strict` on `app/core` and `app/steganalysis`, docstrings in Google style, functions under ~40 lines where possible.
- Tests: `pytest`, backend core coverage ≥ 85%. Every module gets tests in the same phase it is written.
- Determinism: all randomness seeded in scripts (`--seed`, default 1337). Library code that must be reproducible across machines (scatter permutation, whitening) must **not** depend on NumPy RNG stream stability — use the ChaCha20 keystream method in Section 6.3.
- Config via environment variables (`app/config.py`, Pydantic Settings). No magic numbers in the middle of code.
- Logging: structured, no secrets, no file contents, no passwords, no keys, no plaintext, no raw payload bytes, ever.

### 5.2 Security rules
1. **Verify before decrypt.** Signature verification must succeed before any decryption attempt. Never return partial plaintext.
2. **Constant-time comparisons** (`hmac.compare_digest`) for MACs, hashes, fingerprints.
3. **Unique salt and nonce per message** (16-byte random salt, 12-byte random nonce via `os.urandom`). Never reuse a (key, nonce) pair.
4. **No hard-coded keys, passwords or salts** except the clearly named domain-separation labels listed in Section 6.
5. **Stateless server.** No writing uploaded files or messages to disk. Process in memory. No database.
6. **Input validation:** max upload size (default 10 MB), max pixels for embed 4,000,000, max pixels for detect 16,000,000, allowed types checked by actually decoding with Pillow (not just file extension), `Image.MAX_IMAGE_PIXELS` set (decompression-bomb guard).
7. **Rate limiting** on all POST endpoints (e.g., `slowapi`, 30/min per IP default, configurable).
8. **CORS** restricted to configured origins. Security headers (`X-Content-Type-Options`, `Referrer-Policy`, a strict CSP for the frontend build).
9. **Uniform, non-leaky errors** where it matters: wrong stego key and "no hidden data" look identical (`NO_HIDDEN_DATA`). Reason codes for verification failures are allowed in this educational demo, but the threat model must note that a production system would be vaguer.
10. **Dependencies pinned** in lock files; run `pip-audit` and `npm audit` in CI.
11. Private keys are only ever exported **password-encrypted** (PKCS#8 PEM with `BestAvailableEncryption`). The server never keeps them.
12. Never serve user-uploaded content back with a guessable name or inline HTML. Downloads use `Content-Disposition: attachment` with a sanitized filename.

---

## 6. Technical specifications (the heart of the project)

### 6.1 Image I/O rules (`core/stego/image_io.py`)
- Load with Pillow. Accept modes `L` and `RGB`. `RGBA`/`LA`/`P`/`CMYK` → convert to `RGB`/`L` and return a warning string list (for example, "alpha channel discarded"). 16-bit → reject with `UNSUPPORTED_FORMAT`.
- Convert to a NumPy `uint8` array of shape `(H, W)` or `(H, W, 3)`. Flatten with C-order (`reshape(-1)`) to get the **sample vector**; sample index `i` maps to pixel/channel in raster order. This ordering is part of the spec — extractor and embedder must agree.
- Save: PNG, `compress_level=6`, **no** ICC profile, **no** EXIF, no gamma chunk. After saving, re-load and assert the pixel array is identical (round-trip test).
- Reject JPEG for embedding: message "JPEG is lossy; hidden bits would be destroyed. Use PNG/BMP." JPEG is allowed for **detection** with a warning that results are less meaningful.

### 6.2 Stego stream layout

**Embedded stream = `StegoHeader (13 bytes)` ‖ `Packet bytes`.**

```
StegoHeader (13 bytes)
  magic        4  bytes  b"SGST"
  version      1  byte   0x01
  payload_len  4  bytes  uint32 big-endian  (length of Packet bytes)
  crc32        4  bytes  CRC32 of the 9 bytes above (early wrong-key / corruption check; not security)
```

**Capacity:** `capacity_bits = (num_samples − 128) × 1` for keyed mode (128 bits reserved for salt), `num_samples` for sequential mode. Maximum packet bytes = `floor((capacity_bits − 104) / 8)` where 104 = header bits. Maximum *plaintext* bytes = max packet bytes − 128 (packet overhead, Section 6.4).
`bpp = embedded_bits / (H × W)`. Reject with `CAPACITY_EXCEEDED` and tell the user the maximum message size for this image.

**Sequential mode (educational, "naive LSB"):** bits of `header‖packet` (MSB-first per byte) replace/match the LSBs of samples `0, 1, 2, …` in order. No key. Anyone can extract the (still encrypted and signed) packet and the magic bytes are visible in plain LSBs — the UI explains why this is weak for covertness. Also shows why heatmaps localize the modified top rows.

**Keyed mode (default):**
1. Samples `0 … 127`: store a random 16-byte `stego_salt` in their LSBs (always LSB replacement, MSB-first). These 128 samples are excluded from the scatter domain. (A random 128-bit string in the LSBs of the first 128 samples is statistically negligible.)
2. `stego_key = Argon2id(stego_passphrase, salt = SHA256(b"stegaguard/stego/v1")[:16], t=3, m=64 MiB, p=4) → 32 bytes`. The UI default for `stego_passphrase` is "same as message password". This layer is **obfuscation and unlinkability, not confidentiality**; confidentiality comes from AES-GCM.
3. `K_pos ‖ K_wh = HKDF-SHA256(ikm = stego_key, salt = stego_salt, info = b"sg-stego-v1", length = 64)`.
4. Permutation `π` of the remaining `n − 128` samples from `K_pos` (Section 6.3).
5. Whitening: `B' = (header ‖ packet) XOR ChaCha20_keystream(K_wh, nonce = 0, len(B))`.
6. Bit `j` of `B'` (MSB-first) is written to sample `128 + π[j]`'s LSB.
Receiver: read salt → derive keys → rebuild `π` → read 104 header bits (unwhiten) → check magic/version/CRC → read `payload_len` bytes → unwhiten → packet. Magic/CRC failure ⇒ `NO_HIDDEN_DATA`.

**Embedding operations** (given sample value `v` and message bit `b`):
- `lsb_replace`: `v' = (v & 0xFE) | b`.
- `lsb_match` (±1): if `(v & 1) == b` keep `v`; else choose `+1` or `−1` with a fair coin from the keystream/`os.urandom`, except `v==0 → +1` and `v==255 → −1`. Extraction is identical for both methods (read the LSB). Reference: Mielikäinen, "LSB matching revisited" (2006). Note: `lsb_match` randomness does **not** need to be reproducible by the receiver.
Use vectorized NumPy; embedding a 256×256 image must take well under 100 ms.

### 6.3 Keyed permutation (version-independent)
Do **not** use `np.random.permutation` for anything the receiver must reproduce. Instead:
1. Generate `8 × m` bytes of ChaCha20 keystream from `K_pos` (cryptography's `Cipher(algorithms.ChaCha20(key, nonce16), mode=None)`; nonce all zeros is fine since the key is unique per message through the salt) for `m = n − 128` samples.
2. Interpret as `m` unsigned 64-bit integers (`np.frombuffer(..., dtype='<u8')`).
3. `π = np.argsort(values, kind="stable")`. Ties are astronomically rare and handled deterministically by the stable sort.
Test: same key ⇒ same `π` on repeated calls; different key ⇒ different `π`; `π` is a valid permutation. Cap `m` by the 4 MP embed limit so memory stays below ~100 MB.

### 6.4 Crypto packet format (`core/crypto/packet.py`)

```
Packet (big-endian). Overhead = 128 bytes + plaintext length.
  magic        4   b"SGP1"
  version      1   0x01
  flags        1   bit0: payload is a file (filename included), bit1: zlib-compressed before encryption
  kdf_id       1   0x01 = Argon2id, 0x02 = scrypt (fallback)
  reserved     1   0x00
  sender_fp    8   first 8 bytes of SHA-256(raw 32-byte Ed25519 public key)
  salt        16   random, for KDF
  nonce       12   random, for AES-GCM
  ct_len       4   uint32, length of ciphertext (includes the 16-byte GCM tag)
  ciphertext  ct_len
  signature   64   Ed25519 signature over ALL preceding bytes of the packet
```
- **Plaintext inner format:** `kind(1: 0=text,1=file)` ‖ (if file: `name_len(2) ‖ name(UTF-8)`) ‖ `data`. Text is UTF-8.
- **KDF:** Argon2id (`argon2-cffi`, `hash_secret_raw`, time_cost=3, memory_cost=65536 KiB, parallelism=4, hash_len=32). Fallback `Scrypt(n=2**15, r=8, p=1)` if Argon2 is unavailable. Enforce a minimum password length (≥ 8) in the API and show a strength meter in the UI.
- **AEAD:** AES-256-GCM. **AAD = packet bytes from `magic` through `nonce`** (header authenticated as associated data).
- **Signature:** Ed25519 over `packet[:-64]`. Verified with the sender's public key supplied by the receiver (trusted out-of-band; the UI shows the fingerprint and asks the receiver to compare it).
- **Receiver order (strict):** parse → check magic/version/lengths → compare `sender_fp` with the supplied public key's fingerprint (mismatch ⇒ `KEY_MISMATCH`) → **verify signature (fail ⇒ `VERIFICATION_FAILED`, stop)** → derive AES key → AES-GCM decrypt (fail ⇒ `DECRYPTION_FAILED`, meaning wrong password or corruption) → parse inner format.
- **Why both a signature and GCM?** GCM gives confidentiality + integrity for anyone holding the password. The Ed25519 signature adds *sender authentication and non-repudiation* and lets the receiver reject forgeries **before** spending Argon2/AES effort. Explain this in `VIVA_QA.md`.

### 6.5 Key management (`core/crypto/keys.py`)
- `generate_keypair()` → Ed25519 keypair.
- Private key export: PKCS#8 PEM encrypted with the user's key password. Public key export: SubjectPublicKeyInfo PEM.
- `fingerprint(public_key)` → SHA-256 hex of raw public bytes; display as groups of 4 hex chars; also show a short 8-byte form (matches `sender_fp`).

### 6.6 Signed integrity manifest (`core/crypto/manifest.py`)
Produced by the sender after embedding. It is a **separate file** (never embed it, never ship it together with the stego image if covertness matters).

```json
{
  "version": 1,
  "created_at": "2026-11-14T12:00:00Z",
  "cover_pixel_sha256": "…",
  "stego_pixel_sha256": "…",
  "stego_file_sha256": "…",
  "dimensions": [W, H],
  "channels": 3,
  "method": "lsb_replace",
  "mode": "keyed",
  "payload_bytes": 1234,
  "payload_bpp": 0.0123,
  "sender_fingerprint": "…64 hex…",
  "signature": "base64(Ed25519 over canonical JSON of all other fields)"
}
```
- `pixel_sha256` = SHA-256 over `b"H,W,C,uint8|" + array.tobytes()` (so a PNG re-save that preserves pixels still verifies; any pixel change fails).
- Canonical JSON for signing: `json.dumps(obj_without_signature, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()`.
- `/verify` runs **three independent checks** and returns each result: (A) pixel hash matches manifest, (B) manifest signature valid under the public key, (C) embedded packet signature valid (needs stego key/mode to extract). Flipping a single pixel anywhere must fail check A even if the payload still extracts.

### 6.7 Quality metrics (`core/stego/metrics.py`)
MSE, PSNR (dB), SSIM (`skimage.metrics.structural_similarity`, `channel_axis` for RGB), fraction of samples changed, embedded bits, bpp, and an amplified absolute-difference image (×50, clipped) for visualization.
**Sanity tests:** embedding random data at payload `p` bpp with `lsb_replace` should give MSE ≈ `0.5 × p` and PSNR ≈ `51.1 + 10·log10(1/p)` dB (so ≈ 51 dB at 1 bpp, ≈ 61 dB at 0.1 bpp) within a small tolerance.

### 6.8 Classical steganalysis (`steganalysis/classical/`)
Implement from the original ideas, with docstrings that cite the paper (author, year):
1. **Chi-square attack** (Westfeld & Pfitzmann, 1999): compare histogram pairs-of-values `(2k, 2k+1)`; LSB replacement equalizes them. Return statistic, degrees of freedom, p-value (chi² survival function). Provide a **progressive** version over growing row prefixes (for localization in sequential mode).
2. **RS analysis** (Fridrich, Goljan & Du, 2001): groups of 4 pixels (or 2×2), discrimination function (sum of absolute differences), flipping masks `M = [0,1,1,0]` and `−M`; compute `R_M, S_M, R_-M, S_-M` and the quadratic estimate of embedded length `p`. Per channel for RGB.
3. **Sample Pair Analysis** (Dumitrescu, Wu & Wang, 2002/2003): estimate embedding rate `p` from pair statistics.
4. **Hand-crafted feature vector** (per channel, then average and also concatenate min/max across channels):
   - chi-square statistic and log p-value; pair-difference `Σ|h(2k) − h(2k+1)| / N`
   - RS estimate, SPA estimate, and the four RS counts
   - LSB-plane stats: ones-ratio deviation from 0.5, LSB entropy, horizontal and vertical LSB agreement rate (adjacent LSB equality)
   - **SPAM-lite** (after Pevný, Bas & Fridrich, 2010): first-order horizontal/vertical differences clipped to `[−3, 3]`, joint histogram of three consecutive differences (7³ = 343 bins), averaged over directions
5. **Models:** `RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=seed)` primary; `HistGradientBoostingClassifier` secondary. Save with `joblib` + a JSON sidecar listing feature names, training data hash, seed, versions.
6. **No-training fallback:** a rule-based detector from RS/SPA/chi-square estimates so the app works before any model is trained. Clearly labelled "statistical (untrained)" in the UI.

Notes: RS/SPA work on natural images; on synthetic noise or flat images they misbehave. Unit tests that depend on natural-image statistics must use real photo fixtures (small CC0 images you add to `tests/fixtures/`), and use loose thresholds.

### 6.9 Deep steganalysis (`steganalysis/deep/`)
- **Input:** `1×256×256` float32 `= pixel/255`. For larger images: take up to 16 non-overlapping 256×256 tiles evenly spaced; average logits. For smaller than 256: reject for CNN with a clear message (classical detectors still run). RGB: run the CNN on each channel independently and aggregate (mean of logits, also report max) — document as a limitation because the model is trained on grayscale statistics.
- **Fixed high-pass first layer:** the **KV 5×5 kernel** (divide by 12):
```
[[-1,  2,  -2,  2, -1],
 [ 2, -6,   8, -6,  2],
 [-2,  8, -12,  8, -2],
 [ 2, -6,   8, -6,  2],
 [-1,  2,  -2,  2, -1]] / 12
```
  Implemented as a non-trainable `Conv2d(1,1,5,padding=2,bias=False)`. Truncate the residual with `clamp(−T, T)` (T = 3 as default, make it a hyperparameter).
- **Architecture ("StegNet-Lite"), under ~2 M parameters:**
  - Stage 1–3: `Conv3×3 → BatchNorm → ReLU` blocks with **residual connections, 16 channels, NO pooling** (early pooling destroys the faint stego signal; SRNet design insight).
  - Stage 4–6: conv blocks that double channels (32 → 64 → 128) with `AvgPool2d(2)` after each.
  - Global average pooling → `Linear(128, 1)` → logit.
  - Document exact layers in `MODEL_CARD.md`.
- **Training data:** generated **on the fly** in the `Dataset` by embedding into each cover: for every cover produce (cover=0, stego=1) as a **pair in the same batch** (pair-batching is known to stabilise steganalysis training). Training payload bpp sampled from `{0.05, 0.1, 0.2, 0.4, 0.8}`; method mixture 50% `lsb_replace` + 50% `lsb_match`; mode `keyed`; random message bytes; random per-sample key. Validation and test sets use **fixed pre-generated, seeded** stego sets written to disk.
- **Optimization:** AdamW, lr 1e-3 with cosine decay (or OneCycle), weight decay 1e-4, batch 32 pairs (64 images), up to 40 epochs, early stopping on validation loss (patience 8), mixed precision on GPU, gradient clipping 1.0. **Curriculum:** epochs 1–8 use only bpp ≥ 0.4, then add lower payloads. Loss: BCE with logits.
- **Selection metric:** validation ROC-AUC and P_E (see Section 8). Save best checkpoint + `cnn_v1.json` (hyperparameters, seed, git commit hash, training time, dataset split hash).
- **Explainability:** Grad-CAM on the last conv block (hooks), upsampled with bilinear interpolation to input size, plus a model-independent **residual-energy map** (local mean of `|KV residual|`). Return both as PNG heatmaps. State in the UI that heatmaps are indicative, not proof.
- **Calibration:** temperature scaling on the validation set (`calibration.py`); store `T` in the model JSON.

### 6.10 Ensemble and decision (`steganalysis/ensemble.py`)
- Inputs: calibrated CNN probability, RF probability, and normalized RS/SPA/chi-square scores.
- Combine with a logistic-regression **stacker** trained on the validation set (never on the test set), or a documented weighted average if the stacker is not stable.
- Output: `label` (`clean` / `suspected_stego`), `probability`, per-detector breakdown, and an **operating point** selector: `balanced` (threshold maximizing Youden's J on validation) and `low_false_alarm` (threshold at ≤ 1% FPR on validation).

---

## 7. REST API specification

Base path `/api`. JSON in/out unless noted. Errors always use:
```json
{"error": {"code": "CAPACITY_EXCEEDED", "message": "Human-readable message", "details": {}}}
```
Error codes: `INVALID_IMAGE`, `UNSUPPORTED_FORMAT`, `IMAGE_TOO_LARGE`, `CAPACITY_EXCEEDED`, `WEAK_PASSWORD`, `BAD_KEY`, `KEY_MISMATCH`, `NO_HIDDEN_DATA`, `VERIFICATION_FAILED`, `DECRYPTION_FAILED`, `MODEL_UNAVAILABLE`, `RATE_LIMITED`, `INTERNAL`.

| Method & path | Request | Response |
|---|---|---|
| `GET /health` | – | `{status, version, models_loaded:[…]}` |
| `POST /keys/generate` | JSON `{key_password}` | `{public_key_pem, private_key_pem_encrypted, fingerprint, fingerprint_short}` |
| `POST /embed` | multipart: `cover` (file), `message` (text) **or** `message_file`, `password`, `private_key_pem`, `key_password`, `method` (`lsb_replace`\|`lsb_match`), `mode` (`keyed`\|`sequential`), `stego_passphrase?` | `{stego_png_base64, manifest, metrics:{mse,psnr,ssim,bpp,bits_changed_pct,capacity_bits,used_bits}, diff_png_base64, warnings:[]}` |
| `POST /extract` | multipart: `image`, `password`, `public_key_pem`, `mode`, `stego_passphrase?` | `{stages:[{name,status,detail}], verified, plaintext?|file_base64?, filename?}` — plaintext **only** if all stages pass |
| `POST /verify` | multipart: `image`, `manifest` (JSON), `public_key_pem`, `mode?`, `stego_passphrase?` | `{checks:{pixel_hash:{ok,detail}, manifest_signature:{ok,detail}, payload_signature:{ok,detail}|null}, overall_ok}` |
| `POST /detect` | multipart: `image`, `detectors` (`all` or CSV of `statistical,rf,cnn`), `operating_point` | `{label, probability, detectors:{…}, features:{…}, heatmap_gradcam_png_base64?, heatmap_residual_png_base64?, bitplanes:[…optional…], warnings:[], latency_ms}` |
| `POST /detect/batch` | up to 20 images | list of per-image results (same shape, no heatmaps by default) |
| `GET /models` | – | registered models with metadata and headline metrics |
| `GET /results` | – | contents of `results/metrics.json` (for Analytics page) |
| `GET /results/plots/{name}` | – | PNG |

Notes: embed returns base64 inside JSON (simpler for the SPA) but the frontend must offer **byte-exact download** by decoding base64 into a `Blob` — **never** pass the stego image through a `<canvas>` for download (it can alter pixel values). All endpoints enforce limits from Section 5.2. OpenAPI docs come from FastAPI; export a snapshot to `docs/API.md`.

---

## 8. Evaluation methodology (makes the results credible)

### 8.1 Dataset and splits
- **Primary:** BOSSbase 1.01 (Bas, Filler & Pevný, 2011): 10,000 grayscale 512×512 images. Search for it by name (it is mirrored by several academic sources and Kaggle). Resize to 256×256 with Pillow `LANCZOS`, save as 8-bit PNG.
- **If BOSSbase cannot be downloaded:** use BOWS2, or any set of ≥ 3,000 *lossless-origin* photos. If your photos come from JPEG sources (phones, web), **downscale by at least 2× with antialiasing** and convert to grayscale PNG to wash out JPEG block artefacts, otherwise the model may learn JPEG-vs-not artefacts instead of stego. Record the choice in `DECISIONS.md`.
- **Split by cover ID** (70% train / 15% val / 15% test) with a seeded RNG and save `splits.json`. A cover and all its stego versions must stay in the same split (no leakage).
- Optional **RGB test set** from lossless color photos to report RGB performance separately.

### 8.2 Experiment grid (test set)
Methods `{lsb_replace, lsb_match}` × modes `{keyed, sequential}` × payload bpp `{0.05, 0.1, 0.2, 0.4, 1.0}` × detectors `{chi-square, RS, SPA, RF, CNN, ensemble}`. Plus a **mismatch experiment:** train the CNN on `lsb_replace` only and test on `lsb_match` (shows the generalization gap).

### 8.3 Metrics (all saved to `results/metrics.json`)
Accuracy, precision, recall, F1, ROC-AUC, **P_E = min over thresholds of ½(P_FA + P_MD)** (the standard steganalysis error), **TPR at 1% FPR**, confusion matrix at the chosen operating point, and inference latency per image (CPU). Also bootstrap 95% confidence intervals (1000 resamples) for AUC and P_E.

### 8.4 Plots (saved to `results/plots/`)
ROC curves per payload, detection accuracy vs payload per detector, confusion matrices, P_E vs payload (lines for each detector and method), training/validation curves, example Grad-CAM gallery.

### 8.5 Honesty requirements
Report failures plainly. Expect (do not promise): classical attacks and the CNN do well on `lsb_replace` at ≥ 0.2 bpp; everything gets harder at 0.05 bpp; `lsb_match` is harder for chi-square/RS/SPA; the CNN generalizes imperfectly to unseen embedding. Write whatever the numbers actually are.

---

## 9. Build phases

Each phase has: **Goal → Tasks → Files → Acceptance → Stop.** Do not skip the Stop.

### Phase 0 — Scaffold, rules, tooling
**Goal:** a repo where lint, tests and both servers can run (even if empty).
**Tasks**
- Create the layout from Section 4. `git init`, `.gitignore` (data, models weights, `.env`, `node_modules`, `__pycache__`, `*.pem`).
- Write `AGENTS.md` from Appendix A and copy it to `.github/copilot-instructions.md`. (Check your IDE's docs for where it reads workspace rules; keep `AGENTS.md` at the repo root regardless.)
- Backend: `pyproject.toml` (ruff, mypy, pytest), requirements files, `app/main.py` with `/api/health`, config via Pydantic Settings.
- Frontend: Vite React TS + Tailwind, a placeholder home page that calls `/api/health`.
- `Makefile`, `README.md` skeleton, `docs/DECISIONS.md` (copy Section 2).
**Requirements (guidance, use latest stable and pin in lock files):** `fastapi`, `uvicorn[standard]`, `python-multipart`, `pydantic`, `pydantic-settings`, `pillow`, `numpy`, `scipy`, `scikit-image`, `scikit-learn`, `joblib`, `cryptography`, `argon2-cffi`, `slowapi`, `torch`+`torchvision` (CPU for the app), `matplotlib`, `pandas`, `tqdm`; dev: `pytest`, `pytest-cov`, `httpx`, `ruff`, `mypy`, `pip-audit`, `hypothesis`.
**Acceptance:** `make test` runs (even with a single smoke test), `make lint` passes, backend and frontend start, the page shows API health.
**Stop and report.**

### Phase 1 — Crypto core
**Goal:** a fully tested crypto engine implementing Sections 6.4–6.6.
**Tasks:** `kdf.py` (Argon2id + scrypt fallback), `aead.py` (AES-GCM seal/open with AAD), `keys.py`, `signing.py` (sign/verify with Ed25519), `packet.py` (build/parse/verify-then-decrypt), `manifest.py` (create/sign/verify with canonical JSON).
**Tests (pytest + hypothesis):**
- Round trip for random plaintexts (0 B … 1 MB) including empty and Unicode text.
- Wrong password ⇒ `DECRYPTION_FAILED`; wrong public key ⇒ `KEY_MISMATCH`; flip any single bit anywhere in the packet ⇒ verification fails and **decryption is never attempted** (assert with a mock).
- Two encryptions of the same plaintext/password give different salt, nonce and ciphertext.
- Packet overhead is exactly 128 bytes + plaintext length (+16 tag is inside `ct_len`; check the formula in docstring).
- Manifest: tamper any field ⇒ signature invalid; canonicalization is stable across key order.
- Known-answer tests for Ed25519/AES-GCM from published test vectors (RFC 8032, NIST).
**Acceptance:** all tests pass; coverage of `core/crypto` ≥ 90%; mypy strict clean.
**Stop and report.**

### Phase 2 — Stego core
**Goal:** reliable embed/extract implementing Sections 6.1–6.3 and 6.7.
**Tasks:** `image_io.py`, `bitops.py` (bytes↔bits MSB-first), `keystream.py` (ChaCha20 helpers), `scatter.py` (permutation), `header.py`, `lsb_replace.py`, `lsb_match.py`, `embed.py`, `extract.py`, `metrics.py`, `analysis/bitplane.py` and `analysis/diffmap.py`.
**Tests:**
- Round trip for grayscale and RGB, both methods, both modes, random payloads of many sizes, including exactly-at-capacity and one-byte-over (must raise `CAPACITY_EXCEEDED`).
- Save to PNG → reload → extract still works (lossless round trip). JPEG re-save of a stego image ⇒ extraction fails (document this as expected).
- `lsb_match`: pixel values never leave `[0,255]`; every changed sample differs by exactly 1; extraction equals message.
- Wrong stego key or wrong mode ⇒ `NO_HIDDEN_DATA`.
- Keyed mode: changed-sample positions are spread roughly uniformly (test row-wise histogram of changes); sequential mode changes only the top rows for small payloads.
- Metrics sanity tests from Section 6.7.
- Performance: embedding + extraction on 512×512 RGB under 1 s.
**Acceptance:** all tests pass; coverage ≥ 90%; no use of NumPy RNG for anything the receiver must reproduce.
**Stop and report.**

### Phase 3 — Secure sender/receiver pipeline
**Goal:** glue crypto + stego into the two user workflows.
**Tasks:**
- `pipeline.sender_pipeline(cover, message|file, password, private_key, key_password, method, mode, stego_passphrase)` → `(stego_png_bytes, manifest, metrics, diff_png, warnings)`.
- `pipeline.receiver_pipeline(image, password, public_key, mode, stego_passphrase)` → ordered **stages** list: `read_image`, `extract_bits`, `parse_packet`, `check_sender`, `verify_signature`, `derive_key_and_decrypt`. A stage that fails stops the pipeline; later stages are marked `skipped`. Plaintext returned only if everything passed.
- `pipeline.verify_pipeline(...)` for Section 6.6 checks A/B/C.
- A CLI: `python -m app.cli embed|extract|verify|keygen` (demo-friendly, helps viva).
**Tests:** end-to-end happy path; every tamper scenario (one pixel flipped, manifest field changed, wrong key, wrong password, truncated PNG, image re-saved as JPEG, image resized) produces the correct failing stage; the plaintext is never present in any failure result.
**Acceptance:** CLI demo works end to end; tamper tests pass.
**Stop and report.**

### Phase 4 — Dataset and experiment infrastructure
**Goal:** reproducible data for training and evaluation.
**Tasks:**
- `scripts/prepare_dataset.py --src <folder> --out data/covers256 --size 256 --seed 1337`: grayscale + resize + PNG, hash every output, write `splits.json` (70/15/15 by cover ID) and `dataset_card.json` (counts, hashes, origin).
- `steganalysis/deep/dataset.py`: PyTorch `StegoPairDataset` for on-the-fly training (Section 6.9) and `FixedStegoDataset` for reproducible val/test (pre-generated, seeded; write once to `data/fixed/<split>/<method>_<mode>_<bpp>/`).
- A tiny `data/sample/` of ~30 images so tests and the demo run without the full dataset.
**Acceptance:** script runs on the sample folder; splits have zero cover-ID overlap (asserted in a test); fixed sets regenerate bit-identically with the same seed.
**Stop and report.**

### Phase 5 — Classical steganalysis
**Goal:** Section 6.8 implemented, tested, evaluated.
**Tasks:** `chi_square.py` (+ progressive), `rs.py`, `spa.py`, `features.py`, `rf_model.py`, `scripts/train_classical.py`.
**Tests:**
- On natural fixtures: chi-square p-value and RS/SPA estimates are clearly higher for stego at ≥ 0.4 bpp (`lsb_replace`, sequential and keyed) than for covers; estimates for covers stay low. Use loose thresholds and mark expensive ones `@pytest.mark.slow`.
- Progressive chi-square shows the p-value change near the end of the embedded rows in sequential mode.
- Feature vector shape/names are stable and contain no NaN/inf.
**Training run:** train RF (and HistGradientBoosting) on the training split, tune on val, report on test per payload. Save to `models/classical_rf.joblib` + JSON sidecar and results to `results/`.
**Acceptance:** `make train-classical` produces model + metrics; tests pass; honest numbers recorded.
**Stop and report.**

### Phase 6 — CNN steganalysis
**Goal:** a trained CNN detector (Section 6.9).
**Tasks:** `filters.py` (KV kernel), `model.py`, `train.py`, `infer.py` (tiling, per-channel aggregation), `gradcam.py`, `scripts/train_cnn.py`, `notebooks/colab_train_cnn.ipynb` (installs requirements, mounts Drive, calls the script, copies the model back).
**Process:** develop and smoke-test on CPU with a 100-image subset and 2 epochs; then run the real training on Colab GPU. Log training curves. Evaluate on the fixed test sets.
**Tests:** forward pass shape; the KV layer is not trainable; inference on 256×256 and larger images (tiling) works; Grad-CAM output size equals input size; model loads from checkpoint and gives identical logits on identical input; model parameter count is under 2 M.
**Acceptance:** `cnn_v1.pt` + JSON saved; test metrics produced; no train/test leakage; training curves plot saved.
**Stop and report.** (If no GPU is available, finish the pipeline, document it, and let the app run with the classical detectors; mark the CNN as "not trained" in the UI.)

### Phase 7 — Evaluation, ensemble, model registry
**Tasks:** `calibration.py` (temperature scaling), `ensemble.py` (stacker or weighted average, operating points), `registry.py` (discovers models in `models/`, reads JSON sidecars, exposes metadata; app works with whichever models exist), `scripts/evaluate.py` running the full grid of Section 8, producing `results/metrics.json` and all plots, including the mismatch experiment and bootstrap CIs. Write `docs/MODEL_CARD.md` from the real results (intended use, data, metrics, limitations, ethical notes).
**Acceptance:** `make eval` regenerates everything; `metrics.json` validates against a schema used by the API and frontend; plots exist.
**Stop and report.**

### Phase 8 — REST API
**Tasks:** implement all endpoints in Section 7 with Pydantic schemas, the error model, upload validation, rate limiting, CORS, security headers, request-size limits, model loading at startup via the registry, and a `Retry-After` on rate-limit errors. In-memory processing only.
**Tests (httpx `TestClient`):** happy paths for each endpoint; each error code is reachable; oversized, malformed, JPEG-for-embed, over-capacity and decompression-bomb inputs rejected; **log capture test** asserts that passwords, plaintext and PEMs never appear in logs; rate limiting triggers; `/extract` never returns plaintext on failure.
**Acceptance:** OpenAPI docs complete; `docs/API.md` exported; all tests pass.
**Stop and report.**

### Phase 9 — Frontend foundation and core pages
**Design direction:** dark "security console" theme, light theme toggle, restrained cyan/violet accents, monospaced numerals for hashes and metrics (Inter for text, JetBrains Mono for data). Example tokens: background `#0B0F14`, panel `#111827`, border `#1F2937`, text `#E5E7EB`, accent cyan `#22D3EE`, accent violet `#A78BFA`, success `#34D399`, danger `#F87171`, warning `#FBBF24`. Meet WCAG AA contrast; **never rely on color alone** (pair status colors with icons and words); keyboard accessible; responsive from 360 px up; respects `prefers-reduced-motion`.
**Core plumbing:** typed API client, TanStack Query hooks, global error boundary + toast system, loading skeletons, empty states, file-size/type guards on the client, `.env` for `VITE_API_URL`, Vite dev proxy.
**Pages (build these now):**
1. **Home / How it works:** hero with a live canvas animation of the LSB plane "revealing" noise; the three-subsystem explainer; interactive step diagram (encrypt → sign → embed → verify → decrypt; scan → score → explain).
2. **Hide (Sender wizard, 4 steps):** (1) upload cover (dropzone, preview, capacity meter in bytes and bpp); (2) message text or file + password with strength meter; (3) keys — generate a keypair (download encrypted private key + public key, show fingerprint) or paste existing; method/mode selectors with plain-language tooltips ("keyed = harder to detect"); (4) result — before/after slider, amplified difference heatmap, metrics cards (PSNR, SSIM, bpp, bits changed), byte-exact downloads of stego PNG and signed manifest, a clear warning "do not send the manifest with the image if covertness matters".
3. **Extract & Verify (Receiver):** upload stego image, optional manifest, public key (show fingerprint to compare), password, mode. Show a **verification timeline**: each stage animates to pass ✅ / fail ❌ / skipped ⏭ with the reason. Plaintext appears only after all stages pass (copy/download buttons). A "tampered" state is visually dramatic but accessible.
4. **Detect (Defender):** upload any image; show verdict badge, animated **confidence gauge**, per-detector cards, feature table with hover explanations ("chi-square p-value: …"), **heatmap overlay** with opacity slider and toggle between Grad-CAM and residual-energy, and a **bit-plane viewer** (client-side `getImageData`, plane 0–7, per channel; use `createImageBitmap` with `colorSpaceConversion: 'none'`). Operating-point selector.
**Tests:** Vitest + Testing Library for components (gauge, timeline, dropzone validation); Playwright (or your IDE's browser agent) for the Hide → Extract happy path with mocked/real backend.
**Acceptance:** all four pages work against the running backend; responsive on mobile width; Lighthouse accessibility ≥ 90; no console errors.
**Stop and report.**

### Phase 10 — Advanced features (what makes it "advanced")
1. **Arms Race Lab:** choose method (`lsb_replace`/`lsb_match`), mode, and a payload slider (0.01–1.0 bpp) on a sample cover. Left: sender view (live embed with PSNR/SSIM). Right: defender view (each detector's probability). Below: chart of detection probability vs payload for every detector from the real `results/metrics.json`, with a marker for the current slider value. Narrative callouts explain *why* low payloads and LSB matching are harder.
2. **Tamper Lab:** take a verified stego image and apply controlled attacks **in the browser** — flip 1 pixel, flip N random LSBs, JPEG re-compress (quality slider, via `canvas.toBlob`), resize, crop, add noise — then send to `/verify` and `/extract` and show which stages fail. Teaches that LSB is fragile and signatures catch tampering. (This is the *only* place the canvas re-encodes images, and it is intentional.)
3. **Batch Scan:** drag up to 20 images → table (thumbnail, verdict, probability, top detector) with sorting, filtering and **CSV export**; click a row to open the full Detect view.
4. **Analytics:** model comparison (grouped bars), ROC explorer (choose payload/method), P_E vs payload lines, confusion matrices, training curves, and a Grad-CAM gallery — all rendered from `/api/results`. Show confidence intervals and a "how to read this" panel.
5. **Forensic report export:** a print-optimized report page (browser "Save as PDF") for a single detection: image hash, verdict, detector breakdown, heatmaps, model versions, timestamp, limitations statement.
6. **Sequential-vs-keyed explainer:** side-by-side bit-plane/heatmap of the same message embedded both ways, showing localization.
7. **Presenter mode:** `?demo=1` loads prepared sample images/keys (clearly labelled demo keys, never real secrets) so the live demo is one click per step.
**Acceptance:** each feature works with real backend data; Tamper Lab outcomes match the Phase 3 tamper tests; Analytics matches `metrics.json` exactly.
**Stop and report.**

### Phase 11 — Hardening, QA, CI/CD, Docker
**Tasks:** `pip-audit`/`npm audit` clean or documented; fuzz the extractor and packet parser with random/mutated inputs (no crashes, only typed errors); load test `/detect` and `/embed` (document latency and memory); multi-stage Dockerfiles (CPU-only torch in the runtime image), `docker-compose.yml` (backend + frontend served by nginx or Vite preview), health checks; GitHub Actions: lint, mypy, backend tests with coverage, frontend tests, build, audit; pre-commit hooks for ruff and prettier.
**Acceptance:** `docker compose up` gives a working app; CI is green; coverage and latency numbers recorded in `docs/ARCHITECTURE.md`.
**Stop and report.**

### Phase 12 — Documentation, demo and viva material
**Tasks:** finalize `README.md` (what/why, screenshots or GIFs, quick start, commands, structure), `ARCHITECTURE.md` (with Mermaid diagrams), `THREAT_MODEL.md`, `MODEL_CARD.md`, `API.md`, `ETHICS.md`, `DECISIONS.md`, and:
- `DEMO_SCRIPT.md` — a timed 7–10 minute live demo: (1) show a cover; (2) hide a message with signing; (3) show PSNR/diff and that it looks identical; (4) run Detect on cover vs stego at several payloads; (5) show the heatmap; (6) Arms Race Lab — LSB matching and low payload; (7) Tamper Lab — flip one pixel, verification fails; (8) show the crypto packet format and explain verify-before-decrypt.
- `VIVA_QA.md` — at least 30 questions with short, accurate answers written from *this* codebase. Required topics: what steganography vs cryptography vs steganalysis are; LSB replacement vs matching; why PNG not JPEG; what bpp means; how chi-square, RS and SPA work; why a fixed high-pass first layer; why no early pooling; why pair batching; ROC/AUC/P_E; why keyed scatter; why sign *and* AEAD; why verify-before-decrypt; Argon2id vs PBKDF2; why unique nonces; GCM nonce reuse danger; what the manifest protects; limitations (JPEG, resize, adaptive stego); ethics.
**Threat model must cover:** adversaries (passive warden with a detector, active warden who modifies images, malicious sender, wrong-key receiver), assets, assumptions (public key authenticity), attacks considered (statistical detection, tampering, replay of old stego image, brute-forcing weak passwords, oracle leakage from error messages, DoS by large uploads), and residual risks.
**Acceptance:** a fresh clone can follow the README to a running app and reproduce the eval; docs reference real numbers only.
**Stop and report.**

### Phase 13 — Stretch goals (only after everything above is green)
- **2-LSB embedding** (`k=2`) with the capacity/detectability trade-off shown in the Arms Race Lab.
- **Edge-adaptive LSB replacement:** choose embedding positions by local gradient magnitude computed from the **7 most significant bits only** (so the receiver recomputes the same map because replacement never changes those bits); ties broken by the keyed keystream. Note that LSB *matching* would alter the upper bits and break the map; explain this in the docs.
- **Weighted-stego (WS) analysis** estimator as another classical detector.
- **HMAC mode** for symmetric-key authentication as an alternative to Ed25519.
- **Length hiding:** pad plaintext to multiples of 64 bytes (flag bit) so payload size leaks less.
- **Model explanation page:** layer-by-layer view of the KV residual and feature maps.
- Mention (do not implement) content-adaptive schemes (HUGO, WOW, S-UNIWARD), SRNet, and JPEG steganography as future work.

---

## 10. Testing strategy summary

| Level | Tooling | What |
|---|---|---|
| Unit | pytest, hypothesis | crypto, stego, features, models |
| Integration | httpx TestClient | all endpoints, error codes, log hygiene |
| Statistical | pytest (slow mark) | detectors separate stego from cover on natural fixtures |
| Frontend unit | Vitest + Testing Library | gauge, timeline, dropzone, forms |
| E2E | Playwright / IDE browser agent | Hide → Extract → Tamper → Detect journeys, mobile viewport |
| Security | pip-audit, npm audit, fuzz tests, log-capture test | see Section 5.2 |
| Reproducibility | `make eval` | same seed ⇒ same fixed datasets and near-identical metrics |

---

## 11. Definition of done (final checklist)

- [ ] All phases 0–12 completed; stretch goals optional.
- [ ] `docker compose up` runs the full app; `make test` and `make lint` pass; CI green.
- [ ] A message round-trips; one flipped pixel is caught; wrong key/password produce the right errors; plaintext never leaks on failure.
- [ ] Detectors trained (or honestly marked "not trained"); `results/metrics.json` and plots exist and match the UI exactly.
- [ ] Website works on desktop and phone, accessible, no console errors, Presenter mode ready.
- [ ] Docs complete: README, ARCHITECTURE, THREAT_MODEL, MODEL_CARD, API, ETHICS, DECISIONS, DEMO_SCRIPT, VIVA_QA.
- [ ] No secrets, datasets or large weights in git. Licenses and dataset attributions listed in README.
- [ ] The student can explain every module (check `VIVA_QA.md`).

---

## Appendix A — `AGENTS.md` template (copy to repo root and `.github/copilot-instructions.md`)

```markdown
# Agent rules for StegaGuard
Project: AI-Based Image Steganalysis with Cryptographic Verification for Covert Communication.
Source of truth: PROJECT_BLUEPRINT.md. Read it before any work.

## Workflow
- Work one phase at a time. Plan first, implement, run tests+lint, report, then STOP.
- Never start the next phase without the user's "continue".
- Do not re-ask decisions listed in Section 2 of the blueprint.

## Code
- Python 3.11+, type hints, ruff, mypy strict on app/core and app/steganalysis, Google-style docstrings.
- Small, readable functions; comments explain WHY. The student must be able to explain every function.
- core/ and steganalysis/ never import FastAPI. api/ is a thin layer.
- Every module ships with tests in the same phase. Coverage >= 85% on core.
- Frontend: React + TypeScript + Tailwind; no `any`; accessible (WCAG AA); responsive from 360px.

## Security (non-negotiable)
- Verify signature BEFORE decrypt. Constant-time comparisons. Unique salt+nonce per message.
- No hard-coded keys. No secrets, plaintext, passwords or PEMs in logs or git.
- Stateless server: never write uploads or messages to disk.
- Validate uploads by decoding; enforce size/pixel limits; rate-limit POST endpoints.
- Anything the receiver must reproduce (permutation, whitening) uses ChaCha20 keystream, never NumPy RNG.
- Never pass stego images through <canvas> for download; serve exact bytes.

## Honesty
- Never invent metrics. All numbers shown come from backend/results/metrics.json.
- Record deviations from the blueprint in docs/DECISIONS.md.
```

## Appendix B — Phase kickoff prompts (paste one at a time)

1. **Start:** "Read PROJECT_BLUEPRINT.md completely. Summarize your understanding in 10 bullets, list any ambiguities, then begin **Phase 0 only**. Produce a plan and wait for my approval before creating files."
2. **Each next phase:** "Continue with **Phase N** exactly as specified in PROJECT_BLUEPRINT.md. Show a plan first. Write tests with the code. When acceptance criteria pass, report and stop."
3. **Fixing problems:** "Tests in Phase N are failing: <paste output>. Diagnose the root cause, fix the code (not the test) unless the test is wrong, explain the cause in two sentences."
4. **Review:** "Review everything built so far against Sections 5 and 6 of the blueprint. List violations of the security rules, undocumented decisions, and unexplained code that a student could not defend in a viva."
5. **Browser agent (Antigravity or similar):** "Open the running frontend. Execute the Hide → Extract → Tamper journey and the Detect page on cover vs stego images. Report bugs with screenshots and exact steps, then fix them."

## Appendix C — Glossary
- **Steganography:** hiding the *existence* of a message. **Cryptography:** hiding the *meaning*. **Steganalysis:** detecting hidden data.
- **LSB:** least significant bit of a pixel sample. **bpp:** embedded bits per pixel of the cover.
- **Stego / cover:** image with / without hidden data. **Payload:** the hidden bytes.
- **PSNR / SSIM:** image similarity metrics (higher = more similar).
- **ROC / AUC:** detector quality across thresholds. **P_E:** minimum average error ½(false alarm + missed detection).
- **AEAD:** authenticated encryption with associated data (AES-GCM). **KDF:** password → key function (Argon2id).
- **Verify-before-decrypt:** reject forged/tampered data before touching decryption.

## Appendix D — References (verify details before citing in your report or slides)
- Westfeld & Pfitzmann, "Attacks on Steganographic Systems" (1999) — chi-square attack.
- Fridrich, Goljan & Du, "Detecting LSB Steganography in Color and Gray-Scale Images" (2001) — RS analysis.
- Dumitrescu, Wu & Wang, "Detection of LSB Steganography via Sample Pair Analysis" (2002/2003).
- Mielikäinen, "LSB Matching Revisited" (2006).
- Pevný, Bas & Fridrich, "Steganalysis by Subtractive Pixel Adjacency Matrix" (2010) — SPAM features.
- Fridrich & Kodovský, "Rich Models for Steganalysis of Digital Images" (2012) — SRM, high-pass residual idea.
- Bas, Filler & Pevný, "Break Our Steganographic System" (2011) — BOSSbase.
- Xu, Wu & Shi, "Structural Design of Convolutional Neural Networks for Steganalysis" (2016); Ye, Ni & Yi (2017) Ye-Net; Boroumand, Chen & Fridrich, "Deep Residual Network for Steganalysis of Digital Images" (SRNet, 2019).
- RFC 9106 (Argon2); RFC 8032 (Ed25519); NIST SP 800-38D (GCM).
