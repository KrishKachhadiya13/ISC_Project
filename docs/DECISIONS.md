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
