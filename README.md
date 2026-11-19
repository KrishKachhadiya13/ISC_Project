# StegaGuard

**AI-Based Image Steganalysis with Cryptographic Verification for Covert Communication**

An academic project for Information Security & Cryptography (ISC). StegaGuard covers both sides of covert
communication on images:

- **Sender** — encrypts a message with AES-256-GCM (key from Argon2id), signs it with Ed25519, and hides the
  signed packet in the least significant bits of a lossless image (LSB replacement or ±1 matching; keyed
  pseudo-random scatter or plain sequential order).
- **Receiver** — extracts the bits and **verifies the signature before decrypting anything**; every failure
  names the stage that stopped it and no plaintext is ever returned on failure.
- **Defender** — scans any image with classical attacks (chi-square, RS, Sample Pair Analysis), a trained
  feature-based classifier and a CNN with a fixed high-pass first layer, then explains the verdict with
  heatmaps.

The website lets you try each part: Hide a message, Extract & verify, Detect, Compare detectors, Tamper test,
and Batch scan. Measured detector accuracy is documented in `docs/MODEL_CARD.md`.

> **Honesty rule:** every number in the UI and docs comes from `backend/results/metrics.json`, produced by
> `backend/scripts/evaluate.py`. If a detector is not trained, the UI says "not trained". See
> [docs/MODEL_CARD.md](docs/MODEL_CARD.md) for results and limitations.

## Quick start

### Windows, one command (recommended for the demo)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1 -Demo
```

This starts the API on port 8000 and the production UI on <http://localhost:5173> (presenter mode with `-Demo`;
add `-Rebuild` after changing the frontend). Close the window to stop. With the site running, check it end to end:

```bash
cd backend && python -m scripts.smoke_test      # 18 checks: every page route and every API flow
```

### Docker (everything)

```bash
docker compose up --build        # UI on http://localhost:8080
```

### Local development

```bash
# backend (Python 3.11+)
cd backend
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                 # add the CPU/CUDA torch wheel you prefer first
# Windows: install Microsoft C++ Build Tools before pip; pySTC builds its STC extension from C++.
python -m uvicorn app.main:app --reload --port 8000

# frontend (Node 20+)
cd frontend
npm install
npm run dev                                         # http://localhost:5173 (proxies /api to :8000)
```

OpenAPI docs: <http://localhost:8000/docs>. A command-line version of the sender/receiver flow is available:
`python -m app.cli keygen|embed|extract|verify --help`.

### Tests and lint

```bash
make test     # backend (pytest, fast subset) + frontend (vitest)
make lint     # ruff, mypy (strict on core and steganalysis), TypeScript type-check
```

## Live demo

Add `?demo=1` to any URL (for example `http://localhost:5173/hide?demo=1`) for **presenter mode**: one-click
buttons fill the demo cover, message and a throw-away keypair, then carry the result from Hide into Extract &
Verify, the Tamper test and Detect. Demo passwords are fixed public strings; nothing is stored. For a good
detection demo run `python -m scripts.make_demo_assets` once (copies held-out BOSSbase test covers, which are
gitignored). The full timed script is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md); likely examiner questions
are in [docs/VIVA_QA.md](docs/VIVA_QA.md).

## Techniques covered

| Technique | Hide + Extract | Detection results |
|---|---|---|
| LSB replacement (keyed or sequential) | yes | trained on |
| LSB matching ±1 (keyed or sequential) | yes | trained on |
| **2-LSB replacement** (keyed or sequential) | yes, with auto-detection on Extract | unseen: evaluated without retraining |
| **S-UNIWARD** (content-adaptive + STC) | yes | existing detector results are simulator-based; real STC not evaluated yet |
| **HILL** (content-adaptive + STC) | yes | existing detector results are simulator-based; real STC not evaluated yet |

Out of scope: JPEG/DCT-domain schemes and SteganoGAN. The detector simulators reproduce where an adaptive scheme
changes the image but do not carry a message. The Hide page uses syndrome-trellis codes (STC) for real adaptive
messages; stored detector metrics remain based on the simulators until a separate STC evaluation is run.

## Reproducing the models and results

All steps are seeded (default 1337). Run from the repository root with `make`, or from `backend/` directly.

| Step | Command | Output |
|---|---|---|
| Dataset | `make dataset` (BOSSbase 1.01 in `backend/data/raw/BOSSbase_1.01`) | `data/bossbase-prepared/`, `splits.json` (70/15/15 by cover ID) |
| Classical models | `make train-classical` | `models/classical_*.joblib` + JSON, `results/classical_metrics.json` |
| CNN | `make train-cnn` | `models/cnn_v1.pt` + JSON, `results/cnn_metrics.json`, training curves |
| Mismatch CNN | `make train-cnn-mismatch` | `models/cnn_mismatch_replace.pt` + JSON |
| Unseen-technique test sets | `python -m scripts.make_unseen_sets` (before `make eval`) | `data/cnn-fixed/test/` (2-LSB, S-UNIWARD, HILL) |
| Evaluation | `make eval` | `results/metrics.json`, `results/plots/`, `models/ensemble.json` |
| Model card | `python -m scripts.make_model_card` | results sections of `docs/MODEL_CARD.md` |
| API reference | `python -m scripts.export_api_docs` | `docs/API.md` |

BOSSbase 1.01 is not redistributed; download it (for example the Kaggle mirror `lunan0/bossbase-1-01`) and
place the `.pgm` files in `backend/data/raw/BOSSbase_1.01/`. Training the CNN needs a CUDA GPU for reasonable
speed (a 6 GB laptop GPU is enough at the default batch size); notebooks for Colab and Kaggle are in
`backend/notebooks/`. Model weights above 50 MB are not committed.

## Repository layout

```
backend/app/core/         crypto (Argon2id, AES-GCM, Ed25519, packet, manifest) and stego (LSB, scatter, ChaCha20)
backend/app/steganalysis/ classical attacks, features, CNN, calibration, ensemble, evaluation, service
backend/app/api/          thin FastAPI layer: routes, schemas, errors, limits
backend/scripts/          prepare_dataset, train_classical, train_cnn, evaluate
backend/tests/            unit/ and integration/ (API) tests
frontend/src/             pages, components, typed API client, pixel utilities
docs/                     ARCHITECTURE, THREAT_MODEL, MODEL_CARD, ETHICS, DECISIONS, DEMO_SCRIPT, VIVA_QA, API
```

The project is specified in [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md); deviations are recorded in
[docs/DECISIONS.md](docs/DECISIONS.md).

## Security notes

Stateless server (no disk writes, no database), verify-before-decrypt, constant-time comparisons, unique salt
and nonce per message, no secrets in logs (asserted by a test), upload validation by decoding with size and pixel
limits, per-IP rate limiting, strict headers. Details and residual risks: [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Limitations

LSB steganography does not survive JPEG compression or resizing. Detectors are probabilistic and were trained on
grayscale BOSSbase images. Saved S-UNIWARD/HILL detector scores use simulator-generated samples; detector behavior
on real STC messages has not been measured. HUGO, WOW and other content-adaptive schemes remain out of scope.
This is an educational tool, not a production messenger. See [docs/ETHICS.md](docs/ETHICS.md).

## Attributions

STC wrapper: pySTC by Daniel Lerch (MIT), based on Filler, Judas & Fridrich's syndrome-trellis codes.

BOSSbase 1.01: Bas, Filler & Pevný, "Break Our Steganographic System" (2011). Algorithms: Westfeld & Pfitzmann
(1999), Fridrich, Goljan & Du (2001), Dumitrescu, Wu & Wang (2003), Mielikäinen (2006), Pevný, Bas & Fridrich
(2010), Boroumand, Chen & Fridrich (2019). Test fixture `cc0_spruce_forest.jpg` is CC0 (Wikimedia Commons).
