# Ethics and responsible use

StegaGuard is an academic project for Information Security & Cryptography. It demonstrates both sides of
covert communication so that people can understand how it works and how it is detected.

## Intended use

- Learning, coursework, demonstrations and research on **your own images and messages**.
- Evaluating steganalysis methods against a transparent baseline.

## Not intended

- Hiding content you are not permitted to send or possess, or evading lawful monitoring.
- Using a detector score as evidence against a person. The detectors are probabilistic and make mistakes
  (see the false-positive rates and confidence intervals in `results/metrics.json` and `docs/MODEL_CARD.md`).
  A "suspected stego" verdict is a reason to look closer, never proof.
- Production secure messaging. See the non-goals in [THREAT_MODEL.md](THREAT_MODEL.md).

## Dual use

Steganography and steganalysis are dual-use. The embedding code that can hide a message is textbook LSB
replacement, LSB matching and 2-LSB, widely published since the late 1990s and easily detected by the very detectors
in this repository at moderate and high payloads. S-UNIWARD and HILL can carry messages using STC and their cost
maps. Their stored detector results still use separate simulators, so the project makes no claim about detector
performance on real STC messages. Other advanced schemes such as HUGO and WOW are out of scope, and this project
does not claim to defeat modern detectors.

## Privacy

- The server is stateless: uploads, passwords, keys and messages are processed in memory and never written to
  disk or to logs.
- Private keys are returned only in password-encrypted form.
- The demo server necessarily sees passwords and plaintext in order to work. For sensitive use, run it locally.

## Data and attribution

- Detectors were trained and evaluated on **BOSSbase 1.01** (Bas, Filler & Pevný, 2011), obtained through a
  public Kaggle mirror. The dataset is not redistributed in this repository.
- `backend/data/sample/` contains procedurally generated images, not photographs.
- `backend/tests/fixtures/cc0_spruce_forest.jpg` is a CC0 image from Wikimedia Commons used only for unit
  tests.

## Fairness and honesty

All numbers shown in the UI come from `backend/results/metrics.json`, produced by `scripts/evaluate.py`. If a
model is not trained, the UI says so instead of showing placeholder values. Limitations (low payload, LSB
matching, unseen cameras, RGB, adaptive steganography) are stated in [MODEL_CARD.md](MODEL_CARD.md).
