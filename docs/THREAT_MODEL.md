# Threat model

StegaGuard is an educational system. This document states what it defends against, what it assumes, and
what it does not do. It reflects the code in this repository.

## Assets

| Asset | Where it lives | Protection |
|---|---|---|
| Message plaintext | Sender and receiver only | AES-256-GCM; key from Argon2id(password, random salt) |
| Existence of the message | Pixel LSBs of the stego image | Keyed ChaCha20 scatter + whitening (obfuscation, not secrecy) |
| Sender identity / authenticity | Ed25519 signature in the packet and manifest | Receiver verifies against a trusted public key |
| Private signing key | Sender's machine | Only ever exported as password-encrypted PKCS#8 PEM; server never stores it |
| Image integrity | Pixels | Signed manifest with a pixel SHA-256 |

## Adversaries

1. **Passive warden with a detector.** Sees every image and runs steganalysis (chi-square, RS, SPA, ML, CNN).
   *Goal:* flag images that hide data. See [MODEL_CARD.md](MODEL_CARD.md) for how well they do; the honest
   result is that detection works well at high payloads on LSB replacement and degrades at low payloads and
   for LSB matching.
2. **Active warden.** May modify images (re-compress, resize, crop, add noise) to destroy hidden data.
   *Outcome:* LSB steganography does not survive this. The Tamper test page demonstrates it. The signatures make
   the modification *detectable*, not *preventable*.
3. **Malicious sender / forger.** Crafts an image claiming to come from someone else. *Defence:* the receiver
   checks the sender fingerprint, then the Ed25519 signature, before any decryption.
4. **Wrong-key receiver / curious third party.** Tries a wrong password, stego passphrase or public key.
   *Defence:* each failure is reported at the stage where it happens; wrong stego passphrase and "no hidden
   data" are indistinguishable (`NO_HIDDEN_DATA`).
5. **Network/DoS attacker against the demo server.** Large uploads, decompression bombs, floods.

## Assumptions

- The receiver obtains the sender's **public key through a trustworthy out-of-band channel** and compares its
  fingerprint. If an attacker can substitute the key, signatures prove nothing.
- Passwords are chosen with enough entropy. Argon2id raises the cost of guessing; it cannot rescue
  "password1".
- The user's device and browser are not compromised. Python cannot guarantee zeroization of secrets in memory.
- The server operator is trusted *not to be malicious* during a live demo: the server receives passwords and
  plaintext to do its job. For real secrecy, run the backend locally (`docker compose up`) or use the CLI.

## Attacks considered

| Attack | Mitigation | Residual risk |
|---|---|---|
| Statistical detection | Keyed scatter, whitening, LSB matching, and cost-guided S-UNIWARD/HILL with STC | Detectors still catch high LSB payloads; saved adaptive results use simulators, so real STC detection is unmeasured; HUGO and WOW are out of scope |
| Tampering with the stego image | Pixel hash in signed manifest; packet signature; GCM tag | An active warden can still destroy the payload |
| Forged packet | Ed25519 verified **before** key derivation and decryption | Forged *with a compromised private key* is undetectable |
| Replay of an old stego image | None. A valid old image still verifies | Add a timestamp/nonce policy at the application layer if replays matter |
| Brute-forcing a weak password | Argon2id (64 MiB, t=3, p=4), 8-character minimum, strength meter | Short dictionary passwords are still guessable offline from a captured image |
| GCM nonce reuse | Fresh 16-byte salt and 12-byte nonce per message from `os.urandom`, so every key is also unique | None known |
| Error-message oracles | Wrong stego key = no data; the receiver pipeline stops at the first failure; no partial plaintext | The demo reports *which* stage failed, which a production system would hide (see below) |
| Oversized / malicious uploads | 10 MB cap enforced before parsing, pixel limits read from the header (4 MP embed, 16 MP detect), decode-based validation, Pillow bomb guard | Heavy but valid images can still use CPU; rate limit 30 POST/min/IP |
| Log leakage | Access log records method, path, status, latency only; a test asserts passwords, plaintext and PEMs never reach logs | Operator-level access to process memory |
| Secrets in the browser | Keys and passwords live in component state only; nothing is stored in localStorage (only the theme) | Browser extensions or XSS; the nginx CSP forbids inline scripts |

## Deliberate demo trade-offs

- **Detailed failure reasons.** `VERIFICATION_FAILED`, `KEY_MISMATCH`, `DECRYPTION_FAILED`, etc. are shown so
  students can see the pipeline. A production receiver would return one generic failure so an attacker
  cannot learn *which* check failed.
- **Verification before decryption** means a forger learns only "signature invalid" and never gets to
  exercise the password-based path.
- **The manifest is a separate file.** Shipping it with the image reveals that something is hidden.

## Out of scope

JPEG-domain steganography, other content-adaptive schemes (HUGO, WOW), traffic analysis, anonymity, deniability, protection
of metadata outside the image, and any guarantee about memory zeroization.
