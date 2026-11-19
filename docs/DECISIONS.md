# StegaGuard — Architectural and Engineering Decisions

This document records the architectural, technical, and engineering decisions made for the **StegaGuard** project, as established in Section 2 of `PROJECT_BLUEPRINT.md`.

## Pre-Made Decisions (Baseline)

| Topic | Decision | Justification |
|---|---|---|
| Language & Backend | Python 3.11+ with FastAPI, Pydantic v2 | High-performance async API, robust type safety, and direct interoperability with scientific Python. |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS + React Router + TanStack Query + Recharts + Framer Motion | Modern, fast SPA development with strict typing, responsive styling, and animated data visualization. |
| Deep Learning | PyTorch (CPU inference in the application, GPU on Google Colab for training) | Standard framework for modern steganalyzers; lightweight CPU inference avoids heavy local GPU dependencies. |
| Classical ML | scikit-learn (`RandomForestClassifier` primary, `HistGradientBoostingClassifier` secondary) | Interpretable, fast statistical feature classification with cross-validation. |
| Cryptography | `cryptography` (AES-256-GCM, Ed25519, HKDF, ChaCha20, Scrypt fallback) + `argon2-cffi` (Argon2id) | Best-in-class cryptographic primitives with memory-hard password hashing and AEAD. |
| Image Format | Lossless only: PNG (primary), BMP/PGM accepted as input. Output always PNG with metadata stripped. | Lossy formats like JPEG destroy LSB modifications during compression. |
| Pixel Domain | 8-bit. Grayscale (`L`) and RGB supported. RGBA/palette inputs converted to RGB with explicit warning. | Standard 8-bit channel depth required for consistent LSB manipulation. |
| Embedding Methods | `lsb_replace` (core baseline), `lsb_match` (±1, stealthier advanced method) | Demonstrates the arms race between naive replacement and content-preserving matching. |
| Embedding Modes | `keyed` (keyed pseudo-random scatter + ChaCha20 whitening) and `sequential` (educational raster order) | Demonstrates how spatial spreading and whitening evade visual and first-order statistical detection. |
| Bits Per Sample | 1 LSB per sample in core (2 LSBs as stretch goal) | High payload preservation with minimal distortion. |
| Payload Unit | bits per pixel (bpp) of the cover image | Academic standard in steganography and steganalysis literature. |
| Evaluation Payloads | 0.05, 0.1, 0.2, 0.4, 1.0 bpp | Comprehensive evaluation across very low to maximum capacity regimes. |
| Dataset | BOSSbase 1.01 (10,000 grayscale 512×512 images resized to 256×256) | Universal academic benchmark for image steganalysis. |
| CNN Input | Single channel, 256×256 crop. Large images tiled; RGB scored per channel and aggregated. | Consistent input dimensions with high-pass residual filtering. |
| Augmentation | Flips and 90° rotations only. Never resize, JPEG, blur, or brighten. | Pixel-level stego signals are erased by interpolation or lossy transforms. |
| Signature Scheme | Ed25519 (sender keypair) | Fast, 64-byte deterministic signatures resistant to side-channel attacks. |
| Secrets Handling | Server is completely stateless. No keys, passwords, images, or messages stored on disk. | Minimizes attack surface; zero server-side secret persistence. |
| Deployment | Docker + docker-compose; CI with GitHub Actions | Reproducible environments across local development and testing. |

---

## Environment & Platform Notes

1. **Development Host**: Windows 11 with Python 3.13.2 and Node.js v24.18.0.
2. **Cross-Platform Tooling**: Since GNU `make` is not natively installed on standard Windows machines, Windows PowerShell support (`scripts/run.ps1`) is provided alongside the canonical `Makefile` to ensure parity across environments.
3. **Deterministic Permutation**: All pseudo-random scattering and keystream whitening rely exclusively on ChaCha20 keystreams (`cryptography` library) rather than NumPy RNG streams to guarantee platform-independent determinism between sender and receiver.

## Phase 4 Dataset Notes

The checked-in `backend/data/sample/` images are deterministic procedural grayscale
assets for smoke tests and demos only. They are not natural photographs and must
not be used to train or report steganalysis model performance. Real training and
evaluation use the prepared cover workflow with a properly attributed photo
dataset. Fixed validation/test image generation accepts seeded salts and LSB
matching coin bytes so datasets can be regenerated exactly; this deterministic
path is only for offline dataset construction and not live communication.

## Phase 5 Classical Steganalysis

The full BOSSbase 1.01 collection is not checked into the repository or
downloaded to the development laptop. Prepare and train it in Kaggle, with
prepared covers and model/result artifacts under Kaggle's working directory.
The classical training script supports keyed embedding simulation only when a
passphrase is supplied through `STEGAGUARD_TRAINING_PASSPHRASE`; it is never
stored in metadata or printed. Per-variant salts are deterministically derived
from the experiment identity and checked for duplicates so offline training
data can be regenerated while preserving per-message salt uniqueness.
For GitHub handoff, the compact HGB checkpoint and sidecar are tracked; the
Random Forest checkpoint exceeds the 50 MB project limit and remains excluded.
It can be regenerated from the training script and prepared dataset.

The checked-in natural-photo test fixture is a small CC0 Commons image and is
for unit tests only. It is not representative of BOSSbase and its detector
scores are not reported as benchmark performance. Model thresholds are selected
on the validation split; final metrics are calculated on disjoint test covers.

## Phase 6 CNN Steganalysis

**Correction (2026-11-18):** the development laptop does have a CUDA GPU
(NVIDIA GeForce RTX 3050 laptop, 6 GB) and a CUDA build of PyTorch, so the
"CPU-only" statement originally recorded here is out of date. A short
benchmark measured about 13 ms per cover/stego pair for a mixed-precision
training step at the blueprint batch size of 32 pairs (2.9 GiB peak GPU
memory). Generating one on-the-fly keyed pair takes about 76 ms in a single
process because each pair runs Argon2id, so data workers (`--num-workers`)
are needed to keep the GPU fed. The main `cnn_v1` run is therefore trained
locally; the Kaggle notebook remains a supported alternative.

**Mismatch experiment (Section 8.2):** `scripts/train_cnn.py` gained
`--train-methods` (which LSB methods generate training stego; default both)
and `--model-name` (output name; default `cnn_v1`). The mismatch model is
trained with `--train-methods lsb_replace --model-name cnn_mismatch_replace`
and still evaluated on both methods. Non-default names write prefixed files,
so the experiment cannot overwrite `cnn_v1`.

The original note follows. The local Python environment had CPU-only PyTorch and no CUDA device. Phase 6
therefore provides a reproducible 100-cover/two-epoch CPU smoke workflow and
Colab and Kaggle GPU notebooks for full BOSSbase training. Kaggle is provided as
an alternative cloud runtime at the user's request; it uses the same training
script and evaluation protocol as the Colab workflow. The full cloud GPU run has
not yet produced `cnn_v1.pt` or held-out metrics, so the CNN is **not trained**
and its detection results must not be shown as available. Existing classical
models remain the only trained detector artifacts.

The CNN training script pre-generates deterministic validation and test
variants by cover ID, then selects/calibrates using validation only. Fixed-set
manifests record source cover IDs and pixel hashes to prevent stale or
cross-split data from being reused unnoticed. The RGB path scores each channel
independently even though training uses grayscale; explainability heatmaps are
indicative and are not evidence that an image contains hidden data.

## Provisional Phase 7 Work

At the user's request, Phase 7's independent code work may proceed before the
Phase 6 Kaggle run has produced outputs. This is a sequencing deviation only:
CNN-dependent evaluation, benchmark metrics, plots, ensemble validation
thresholds, and result-based model-card updates remain pending until the real
Kaggle artifacts are reviewed. No provisional or smoke-test values may be
presented as benchmark results.

## Phase 8 API decisions (2026-11-18)

1. **Rate limiter.** `slowapi` is listed in requirements but the API uses a small in-process sliding-window
   limiter (`api/limits.py`). It is easier to explain and test, and returns `Retry-After`. It is per worker
   process; a multi-instance deployment would need a shared store.
2. **Uploads never touch disk.** Starlette spools multipart files larger than 1 MB to temporary files by
   default. `keep_uploads_in_memory()` raises that threshold above the request-size cap, which is enforced
   before parsing, so the stateless-server rule holds.
3. **Pixel limits before decoding.** Image dimensions are read from the header and compared with the 4 MP
   (embed) and 16 MP (detect) limits before pixels are decoded, so decompression bombs are refused cheaply.
4. **Stage failures are HTTP 200.** `/extract` reports a failed receiver stage inside a normal response so the
   UI can render the timeline. Input errors (bad key PEM, bad image, weak password) use the error envelope.
5. **`/verify` check C is optional.** Without a `mode` (and, for keyed mode, a stego passphrase) the embedded
   packet cannot be located, so `payload_signature` is `null` and does not block `overall_ok`; the pixel hash
   and manifest signature already bind the exact image.
6. **Detector service.** `app/steganalysis/service.py` loads whichever trained models exist. A corrupt artifact
   disables only itself. With no validated ensemble the best single trained detector decides at its own
   validation threshold and the response says so. The CNN threshold stored in `cnn_v1.json` is a raw logit and
   is converted to a calibrated probability when loaded.
7. **scikit-learn pinned to 1.6.1** because the committed `classical_hgb.joblib` was pickled with that version;
   unpickling with another version is not guaranteed to be valid.
8. **Parallel fixed-set generation.** `train_cnn.py --fixed-workers N` builds the fixed validation/test sets in
   parallel processes. Each set takes every random value from its own condition seed, so contents are identical
   regardless of order. Source-cover hashes are cached across conditions.
9. **Data-loader memory.** Six data workers on a 16 GB laptop ran out of memory (OpenBLAS allocation failures)
   while other applications were open. Training now sets `OPENBLAS_NUM_THREADS=1` and uses five workers.

## Phase 7 evaluation decisions

1. **Ensemble.** A one-parameter weighted average of the classical model and the CNN, with the weight chosen
   by validation ROC-AUC on a 0.1 grid, instead of a logistic-regression stacker. One parameter is easy to
   explain and cannot overfit the validation set the way a flexible stacker can.
2. **Fixed-set scoring.** Covers are identical across the 20 conditions of a split, so each cover is scored once
   and cached by SHA-256.
3. **Classical-model provenance.** The classical models were trained in an earlier Kaggle run on the same
   BOSSbase split, with its own stego keys. Evaluation scores them on this project's fixed test sets; the test
   covers are cover-disjoint from both training runs.
4. **Frontend.** React + Vite + Tailwind with CSS-variable theming (dark default, light toggle). Charts use
   Recharts. The Tamper test page encodes lossless attacks with a small PNG encoder in `lib/pixels.ts`; only
   lossy attacks (resize, JPEG) go through a canvas, which is intentional.

## CNN training fixes (2026-11-18)

A first full run was stopped after five epochs because of two problems found in the logs:

1. **Checkpoint selection was too easy.** Validation used only LSB replacement at 0.4 bpp. That score saturates
   in epoch 1 (AUC 0.989), so the "best" epoch was one that had never seen the low payloads the project is about,
   and early stopping (patience 8) could have ended training around epoch 11. Selection now pools four
   validation conditions (replacement 0.1 and 0.4 bpp, matching 0.2 and 0.4 bpp, keyed). The operating threshold
   and the temperature are fitted on the same pooled validation logits. Early stopping may only trigger after the
   eight curriculum epochs (`CURRICULUM_EPOCHS`).
2. **Training data was ~8× slower than the GPU needed.** About 95% of the cost of one on-the-fly pair was a
   memory-hard Argon2id run on a random throw-away passphrase. `embed(..., stego_key=...)` now accepts a random
   32-byte key and goes straight to the HKDF step (`scatter.expand_stego_key`). A uniformly random key has exactly
   the distribution Argon2id's output is meant to have, so the embedded patterns are statistically identical;
   a test compares both paths. The fast path is used only by the training dataset: live embedding, the API, the
   CLI and the fixed validation/test sets still use the passphrase + Argon2id path. Measured: 76 ms → 9 ms per
   pair in one process.

### Learning rate and diagnostics (second CNN run)

The second run (fast data path, pooled validation) still diverged: pooled validation AUC fell from 0.914 (epoch 2)
to 0.728 (epoch 5) and validation loss rose from 0.47 to 6.9 while training loss kept falling. A diagnostic on the
best saved checkpoint showed the fixed validation sets and freshly generated training-style pairs give the same AUC
in every condition (for example replacement 0.4 bpp: 0.9875 vs 0.9878), so neither the data nor the evaluation
pipeline was at fault. The gradient clipping and mixed-precision code were checked and are correct. That leaves
optimisation instability at the blueprint's learning rate of 1e-3, so:

- the default learning rate is now **3e-4** with a 200-step linear warmup (`--learning-rate`), a deviation from
  the blueprint's 1e-3, recorded in `cnn_v1.json`;
- per-condition validation AUC is logged every epoch, and the newest weights are saved next to the best ones
  (`*_last.pt`), so any further collapse can be inspected.

## Technique range extension (2026-11-19)

The project originally covered one family (LSB, two methods × two modes). Added, in order of value for effort:

1. **2-LSB replacement** (`lsb2_replace`, recoverable). Each selected sample carries two message bits, doubling
   capacity. The stream format is unchanged (same salt, header and packet); only the number of bits written per
   sample differs. The receiver may be told the technique or **auto-detect it**: `extract_auto` tries 1-bit then
   2-bit and relies on the stream header's magic, version and CRC32 to reject a wrong guess (a 2^-32 chance of a
   false accept, and every failure is the same `NO_HIDDEN_DATA`). Exposed as `technique` (`auto|lsb|lsb2`) on
   `/extract` and `/verify`; the response reports the detected technique.
2. **S-UNIWARD and HILL simulators** (`app/core/stego/simulate.py`). They are detection-testing tools only: they
   reproduce where an adaptive scheme changes the image (cost function + entropy-matched ternary change
   probabilities) but carry no recoverable message, because a real implementation needs syndrome-trellis codes.
   Costs are implemented from the published formulas, so values are close to, not bit-identical with, the
   reference Matlab code. Daubechies-8 coefficients are validated by a test (sum √2, unit energy, orthogonality).
3. **Unseen-technique evaluation.** The detectors are **not retrained** for the new techniques. `scripts/make_unseen_sets.py`
   builds fixed TEST sets only (never validation, so ensemble weights and thresholds are unchanged) and
   `scripts/evaluate.py` scores them, showing how far each detector generalises. 2-LSB uses the full 1,500-image
   test split; the simulators use a fixed 500-image subset because each image costs about 0.25 s.

Not done, deliberately: DCT/FFT-domain embedding, edge-adaptive LSB, a mixed-technique retrain, and the
mismatch experiment (optional, skipped at the owner's request; the model card says it was not run).

## Website restyle (2026-11-19)

The first interface used a flat neon-cyan "console" look that read as a generic template; a second attempt overcorrected into
something plain. The current design aims for professional but with character: a **dark-first** deep-navy theme with soft
layered glows and a faint blueprint grid, one periwinkle accent plus a warm amber highlight, glass-style cards with hairline
borders, a proper hero with an informative animated bit-plane figure, a process strip, icon tiles, and subtle scroll reveals
(disabled for people who prefer reduced motion). Fonts: Plus Jakarta Sans (headings), Inter (text), JetBrains Mono (data).
A light theme is available from the header toggle. Both themes meet WCAG AA (checked numerically for every text and
background pair, including text on the translucent card fill). Copy stays in plain language (for example "Arms Race Lab" is
now "Compare detectors", "Analytics" is "Results", and each detector has an ordinary name) while **route paths are
unchanged**. The home, footer and About pages state that this is an ISC course project for educational use. Project details
such as institution, team, supervisor and year live in `frontend/src/lib/project.ts`; empty fields are not displayed, so no
details are invented. Tailwind CSS drives all styling through CSS-variable tokens (`src/styles/index.css`,
`tailwind.config.ts`).

At the owner's request the website no longer mentions the course, the project, or its educational purpose: the top strip,
the home-page chip and notice, the course-mapping section, the footer course text and the project-details block were all
removed, the page title is plain "StegaGuard", and the tagline is a neutral description instead of the full project title.
`frontend/src/lib/project.ts` now holds only the site name, tagline and plain detector names. The About page keeps the
limitations, acceptable use, privacy, models and references. The documentation in `docs/` is unchanged and still describes
the work as a course project.

The Results page was removed from the website (navigation, route, the chart on "Compare detectors" and the charting
library) at the owner's request: model evaluation tables read as lab-report material on a tools site. The numbers are
unchanged and live in `results/metrics.json` and `docs/MODEL_CARD.md`; the API endpoints `/api/results*` remain for
anyone who wants them. The Detect and Home pages now describe detector strength in plain words instead of linking to
the removed page.

### "Prove the message is hidden" panel (Hide result)

Because a hidden message is invisible by design, the Hide result now shows evidence instead of asking viewers to trust it:
the manifest's pixel fingerprints of the cover and the new image (they differ), the 8×8 patch of raw pixel values where the
message left the most changes (found with a summed-area table; changed cells highlighted and announced to screen readers;
one changed pixel shown in binary), and a live read-back that sends the exact PNG bytes, the password and the public key
to `/extract`, with a wrong-password test. The read-back needs the public key, so it is offered only when the key pair was
generated in the wizard; users who bring their own private key are pointed to Extract & verify. The public key can also be
downloaded again from the result screen. Pure logic is in `frontend/src/lib/proof.ts` with tests.


## 2026-11-19: Proof panel explanation is method-aware

## 2026-11-19: Message-carrying S-UNIWARD and HILL use STC

The Hide page now exposes S-UNIWARD and HILL as real embedding methods. Their additive cost maps are fed to the
MIT-licensed `pystcstego` C++ implementation of syndrome-trellis codes; the common SGST header and signed packet
are the STC message. The receiver uses the same keyed ChaCha20 sample ordering, then decodes the payload without
knowing the original cover. The wrapper uses a 64-sample/32-bit length frame;
capacity reporting reserves this frame and the common stream header. Keyed mode still reserves its independent
16-byte salt and whitens the stream.

**Build requirement:** the pinned `pystcstego` Git revision compiles a native C++ extension; the PyPI source
archive omits required headers. Docker installs a compiler in its disposable builder stage. Windows local
installs require Microsoft C++ Build Tools. The adapter calls the pinned wrapper's lower-level encoder and
decoder so both sides use the project's ChaCha20 order directly, without a second Python-random shuffle.

**Evaluation caveat:** `results/metrics.json`, model weights and the model card were not regenerated. Their
S-UNIWARD/HILL rows still refer to simulator-generated detection sets. Detector performance on real STC
embeddings remains a separate, unmeasured experiment; no result is inferred from the simulator.

## 2026-11-19: Proof panel explanation is method-aware
The first version of the "Prove the message is hidden" panel said "only the last digit differs" for every method. That is only true for LSB replacement. `explainChange` in `frontend/src/lib/proof.ts` now describes the chosen method: replacement (last digit), 2-LSB (last one or two digits), matching (±1 move that can carry into several digits). The pixel fingerprints, read-back and wrong-password test do not depend on the method.

## 2026-11-19: Receiver auto-detects placement mode
The Extract page no longer asks for the embedding mode or technique. `/api/extract` and `/api/verify` accept `mode=auto` (now the default for extract): the server tries keyed placement, then sequential, and the existing header CRC rejects a wrong guess. The response reports the `mode` that worked. Secrets (message password, sender public key, optional separate passphrase) cannot be inferred from the image and stay as inputs; the passphrase moved under "Advanced". Done in the API layer only so the core stego modules (being changed for STC) were untouched.

## 2026-11-19: Detect and Extract page pass, optional STC, demo payload
- **Detect:** verdict now reads "Likelihood score" with the flagging line marked; per-detector scores, model names (`classical_hgb`, `cnn_v1`, ensemble) and the measurements table moved into a collapsed "Technical details"; the operating point is shown as "Sensitivity"; the bit-plane view moved below the result inside a collapsed section; a flagged result links to Extract & verify.
- **Extract:** failures give one plain sentence (`frontend/src/lib/receive.ts`, tested) instead of a raw code; JPEG upload warning; copy failure handled; the three manifest checks have plain names.
- **Navigation:** the layout scrolls to the top on every route change, and a new result is scrolled into view and focused (`useRevealOnResult`).
- **Demo payload (measured, not assumed):** on the live detectors, hiding 1,000+ characters in a BOSSbase cover was flagged at >=0.99 (LSB replacement and matching), while 200 characters scored 0.67 and 0.51 against a 0.693 threshold, i.e. not flagged. Presenter mode therefore has a second Hide button with a ~1,100 character message so the Detect demo is meaningful. The short message stays the default for the Extract story. Short messages slipping past the detectors is a real limitation and is stated on the page.
- **STC is optional at runtime:** `pystcstego` needs Microsoft C++ Build Tools on Windows and did not build with MinGW here, so `app/core/stego/adaptive.py` imports it lazily. Without it the backend starts normally, S-UNIWARD/HILL embedding returns `STC_UNAVAILABLE` (HTTP 501), receiving is unaffected, and the seven tests that need the real package are skipped. With the package installed (Docker, or Windows with Build Tools) nothing changes.

## 2026-11-19: Page review round 2 (Tamper, Compare, Batch, How it works)
Found by walking the live pages and fixed in the frontend only:
- **Tamper test** no longer asks for the placement mode; it sends `mode=auto, technique=auto` like Extract, so it also
  works on any image the receiver can read (S-UNIWARD/HILL images when the optional STC package is installed; not
  testable on this machine). The result card now gives one plain headline: intact, "intact but the image was
  altered" (message verifies, pixel hash fails), or lost with the reason from `lib/receive.ts`. Raw error codes and
  the A/B/C check labels were replaced by the shared `CheckRow` component used by Extract.
- **Compare detectors** uses the same words as Detect ("Not flagged / Hidden data suspected", "Original / With
  message"), explains bpp, and has a presenter helper for the demo cover.
- **Batch scan** shows the plain detector name and "Score", states the flagging line, and scrolls to a row's
  details when opened.
- **How it works** tells visitors to select a step, and its Decrypt step no longer implies that a wrong password
  always reaches the GCM check (in keyed mode it never finds the message). About's failure-message line was updated
  to match. Home's "Try the demonstration" now opens presenter mode.
- Deliberately left as is: About/Home still describe S-UNIWARD and HILL as available methods (true only where the
  optional STC package is installed), and Compare's headline about matching being hardest is unchanged. Both were
  raised in the review and not requested.


## 2026-11-19: S-UNIWARD and HILL on Compare detectors
Compare detectors now offers "S-UNIWARD (STC)" and "HILL (STC)" next to the three LSB methods, using the real message-carrying
embedder (not the detection simulator). The random message is sized with 64 extra reserved bits for the STC length field
(`messageLengthFor`, tested). Selecting either shows a warning that the detectors were trained on plain LSB hiding only and
that their performance on real S-UNIWARD/HILL messages has not been measured, so the scan is an example, not a benchmark.
Without the optional `pystcstego` package the scan stops with the `STC_UNAVAILABLE` message and the other methods are
unaffected. Not exercised end to end on this machine because the package could not be compiled here.

## 2026-11-19: STC installed and verified on the build machine; branch repair
- **STC now builds and runs here.** The earlier failure was a 32-bit MinGW (`C:\MinGW`) against a 64-bit Python, which can never
  work. Microsoft C++ Build Tools 2022 were installed with winget and the pinned `pystcstego` revision built into
  `backend/.venv`. All 240 backend tests now pass with none skipped, including the S-UNIWARD/HILL round trips through the
  library and the API. This supersedes the "not exercised end to end on this machine" notes in the two entries above.
- **Live checks:** real S-UNIWARD and HILL messages hide, auto-extract and verify, and appear on Compare detectors. At
  0.4 bpp on the three demo covers the detectors flagged LSB matching 3/3 and S-UNIWARD/HILL 0/6 (ensemble 0.17 to 0.59
  against a 0.693 line). This is an anecdote on three images, not a benchmark, and is not written to `metrics.json`.
- **Tamper behaviour differs by method:** flipping one pixel leaves a plain-LSB message readable, but on an STC image it
  broke the signature in 4 of 4 runs, because every pixel takes part in decoding. The Tamper page text says so.
- **Wording bug fixed:** the extract stage said "0-bit LSB" for STC; it now says "adaptive STC" (pinned by a test).
- **Branch state found and repaired.** While the installer ran, the worktree was switched to `publish-yashwanth` (6 commits
  from base `9f182fa`, pushed to origin). That branch lacked 71 files tracked on `main` (core modules such as
  `image_io.py`, `lsb_match.py`, the detector modules, the classical model weights) and carried an older
  `crypto/packet.py` without `ParsedPacket`, so the backend could not import. 64 of the 71 were restored (staged, not
  committed) from `main`; the other 7 (`AGENTS.md`, `PROJECT_BLUEPRINT.md`, `.github/copilot-instructions.md`, `Makefile`,
  `frontend/src/index.css`, two zip files) were deleted in the laptop worktree before the publish and were left out on
  purpose; `packet.py` was restored from the laptop stash. Not yet committed or pushed, so the published branch is still
  incomplete until that is done. The publish `.gitignore` also now ignores `*.joblib`, so the classical model weights are
  present locally but excluded from git; decide whether that is intended.

