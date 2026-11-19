# Live demo script (about 9 minutes)

## Presenter mode (recommended)

Open any page with `?demo=1`, for example `http://localhost:5173/hide?demo=1` (or `:8080` under Docker). A
violet banner appears and one-click helpers are added:

| Page | Helper | What it does |
|---|---|---|
| Hide | **Fill demo cover, message and keys** | Loads the demo cover, fills message and passwords, generates a fresh throw-away keypair, and jumps to the last step. Press **Hide message**. |
| Extract & Verify | **Load the image from the Hide step** | Fills the stego image, public key, password, mode and manifest from the Hide result. |
| Tamper test | same | Same hand-off; then pick an attack. |
| Detect | **Load the demo cover** / **Load the stego image from Hide** | Fills the image to scan. |

The passwords are fixed public demo strings and the keypair and stego image live only in browser memory (never
localStorage). Use the in-app navigation, not the address bar, between pages, because a reload clears the memory.

**One-time setup for a good detection demo** (from `backend/`):

```bash
python -m scripts.make_demo_assets      # copies 3 held-out BOSSbase test covers to frontend/public/demo/
```

The detectors were trained on BOSSbase-style images. The bundled fallback cover (a small JPEG-origin CC0 photo)
works for the crypto steps, but a detector can wrongly flag even its clean version; the Detect page warns when
the fallback is in use. For a clear Detect demo, hide a message of about 1 KB (≈0.14 bpp on a 256×256 cover)
and check beforehand that the cover scans "clean" and the stego "suspected". Rehearse this once: a detector
verdict on a single image is an anecdote, and `docs/MODEL_CARD.md` has the real test-set results (the website does not show them).

## Detailed script

**Before you start:** backend and frontend running (`docker compose up --build`, or `uvicorn` + `npm run dev`),
a 256×256-or-larger PNG cover ready, a second window with `docs/VIVA_QA.md` open. Check the Home page shows
which detectors are trained; say so out loud ("the CNN is trained / not trained") before relying on it.

| Min | Step | What to do | What to say |
|---|---|---|---|
| 0:00 | **Frame it** | Home page | Three parts of the title: hide (covert communication), verify (cryptography), detect (steganalysis). The animation is bit-plane 0 of an image turning to noise as bits are written. |
| 1:00 | **1. Show a cover** | Hide → upload the PNG | The capacity meter is computed from the same formula as the backend: samples − 128 salt bits − 104 header bits, minus 128 bytes of packet overhead. |
| 2:00 | **2. Hide with signing** | Type a message, password; generate a keypair; method *LSB replacement*, mode *Keyed*; press Hide | Argon2id → AES-256-GCM → Ed25519 → keyed scatter. Download the **encrypted** private key and public key. Note the fingerprint. |
| 3:00 | **3. Looks identical** | Result step | PSNR ≈ 70+ dB at this tiny payload, SSIM ≈ 1. Drag the before/after slider. Show the ×50 difference map: a sparse speckle spread everywhere (keyed). Offer: "sequential mode would put it all in the top rows." |
| 3:30 | **3b. Prove it** | Scroll to *Prove the message is hidden* on the Hide result | (1) The two pixel fingerprints differ. (2) The 8×8 patch of raw pixel values: highlighted cells changed by exactly 1, and in binary only the last digit differs. (3) Press **Read the message back**: all six stages pass and the original text returns, read from the exact PNG. Then **Try a wrong password**: stage 2 fails, nothing comes back. |
| 3:45 | **4. Defender view** | Detect → upload cover, scan; then the stego | Verdict, gauge, each detector separately. Say what each means. At this very low payload expect "clean" for both. That is honest. |
| 4:45 | **5. Heatmap / bit planes** | Detect page | Bit-plane 0 of the stego image: noise where bits were written. Heatmap: where the CNN responded (indicative, not proof). |
| 5:30 | **6. Arms race** | Compare detectors: same cover, slide to 0.4 bpp, replace vs match | Left: sender metrics. Right: detector probabilities cover vs stego. Chart below is **test-set** behaviour from `metrics.json`, with your slider position marked. LSB matching and low payload are where hiding wins. |
| 6:30 | **7. Tamper** | Extract & Verify with the correct inputs (all stages ✔). Then Tamper test: *Flip 1 pixel* | One flipped pixel fails check A (pixel hash) while the payload may still extract. Then *JPEG re-compress*: payload destroyed. LSB is fragile; the signatures make tampering *visible*. |
| 8:00 | **8. Verify before decrypt** | How it works → packet table | Strict order: parse → fingerprint → **signature** → derive key → decrypt. A forged packet never reaches Argon2 or AES. Why both a signature and GCM: see VIVA_QA. |
| 9:00 | **Close** | About page | Limitations and ethics. Offer questions. |

## If something goes wrong

- *Backend offline badge:* start `uvicorn app.main:app --port 8000`; the UI recovers on the next request.
- *"CNN not trained":* expected until `models/cnn_v1.pt` exists. The statistical and classical detectors still work.
- *Rate limited (429):* wait for the `Retry-After` seconds, or restart the backend for a fresh window.
- *Slow first request:* Argon2id uses 64 MiB and ~0.3 s by design.

## Suggested covers

Use a real photo for the detection steps, not a synthetic gradient: RS and SPA assume natural-image statistics.
A BOSSbase image resized to 256×256 works well. Never demo with real secrets; use throw-away passwords.
