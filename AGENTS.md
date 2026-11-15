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
