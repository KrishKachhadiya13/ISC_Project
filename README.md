# StegaGuard — AI-Based Image Steganalysis with Cryptographic Verification for Covert Communication

> Academic project for Information Security & Cryptography (ISC).
> Master specification: [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md).

StegaGuard is an end-to-end research and demonstration platform exploring the steganographic arms race between covert communicators and defensive steganalyzers.

---

## Architecture Overview

StegaGuard unites three primary subsystems into an integrated full-stack application:

1. **Covert Communication (Stego Engine)**:
   - Lossless 8-bit image embedding via LSB Replacement and LSB Matching ($\pm 1$).
   - Modes: Educational sequential embedding and cryptographically keyed pseudo-random scatter with ChaCha20 whitening.
2. **Cryptographic Verification (Crypto Engine)**:
   - Argon2id key derivation, AES-256-GCM authenticated encryption (AEAD).
   - Ed25519 digital signatures and signed integrity manifests.
   - Enforced **verify-before-decrypt** pipeline preventing unauthorized decryption attempts.
3. **AI-Based Image Steganalysis (Detection Engine)**:
   - Classical statistical attacks: Chi-square analysis, RS analysis, Sample Pair Analysis (SPA), and SPAM-lite features with Random Forest.
   - StegNet-Lite CNN: Non-trainable high-pass KV filter first layer, residual blocks without early pooling, and Grad-CAM / residual-energy explainability heatmaps.
   - Calibrated ensemble scoring with configurable operating points.

---

## Repository Structure

```
stegaguard/
├── .github/workflows/ci.yml       # CI/CD pipeline
├── AGENTS.md                      # Operational rules for AI agents
├── PROJECT_BLUEPRINT.md           # Master project specification
├── README.md                      # This file
├── Makefile                       # Unix make commands
├── scripts/run.ps1                # Windows PowerShell execution helper
├── docker-compose.yml             # Container orchestration
├── docs/                          # Architecture, Threat Model, Model Card, API docs
├── backend/                       # FastAPI application & ML/Stego engines
│   ├── app/
│   │   ├── api/                   # REST API routes and schemas
│   │   ├── core/                  # Pure crypto, stego, and pipeline modules
│   │   └── steganalysis/          # Classical and deep detection models
│   ├── scripts/                   # Dataset preparation, training, and evaluation
│   ├── tests/                     # Unit and integration test suites
│   ├── models/                    # Model registry and weights (gitignored)
│   └── results/                   # Evaluation metrics and plots
└── frontend/                      # React 18 + Vite + TypeScript + Tailwind CSS UI
```

---

## Quick Start

### Prerequisites
- Python 3.11+ (Python 3.13 supported)
- Node.js 18+ (Node 24 supported) & npm

### Backend Setup
```bash
cd backend
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` to access the StegaGuard console.
