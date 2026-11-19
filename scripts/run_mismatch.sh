#!/usr/bin/env bash
# Autopilot for the Section 8.2 mismatch experiment:
#   train a CNN on LSB replacement only -> re-run the evaluation -> regenerate the model card.
#
#   bash scripts/run_mismatch.sh
# Log: backend/data/logs/mismatch.log   Summary: backend/data/logs/MISMATCH_STATUS.md
#
# It never commits, never pushes, and leaves cnn_v1 and its files untouched
# (the second model is written under its own name, cnn_mismatch_replace).

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACK="$ROOT/backend"
LOGS="$BACK/data/logs"
PY="$BACK/.venv/Scripts/python"
LOG="$LOGS/mismatch.log"
STATUS="$LOGS/MISMATCH_STATUS.md"
mkdir -p "$LOGS"
cd "$BACK" || exit 1

# One BLAS thread per process: more than that ran this laptop out of memory before.
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
status() { printf '# Mismatch experiment status\n\nUpdated: %s\n\n%s\n' "$(date '+%F %T')" "$1" > "$STATUS"; }

: > "$LOG"
log "mismatch autopilot started"
status "RUNNING: training cnn_mismatch_replace (20 epochs, replacement only)."

# 1. Train. 20 epochs instead of 40 keeps it inside the time budget; the schedule is
#    recorded in the model's JSON, and the model card states it.
"$PY" -u -W ignore -m scripts.train_cnn --dataset data/bossbase-prepared \
  --models-out models --results-out results --fixed-out data/cnn-fixed --device cuda \
  --num-workers 3 --fixed-workers 2 --epochs 20 \
  --train-methods lsb_replace --model-name cnn_mismatch_replace >> "$LOG" 2>&1
code=$?
log "training exit $code"
if [ $code -ne 0 ] || [ ! -f results/cnn_mismatch_replace_metrics.json ]; then
  status "FAILED: training did not finish (exit $code). cnn_v1 results are unchanged. See backend/data/logs/mismatch.log."
  exit 1
fi

# 2. Re-evaluate everything so metrics.json gains the mismatch section.
status "RUNNING: re-evaluating (adds the mismatch section to metrics.json)."
"$PY" -u -W ignore -m scripts.evaluate --fixed data/cnn-fixed --workers 4 >> "$LOG" 2>&1
code=$?
log "evaluate exit $code"
if [ $code -ne 0 ]; then
  status "PARTIAL: the mismatch model trained but re-evaluation failed (exit $code). Run: python -m scripts.evaluate --fixed data/cnn-fixed"
  exit 1
fi

# 3. Model card from the new metrics.
"$PY" -W ignore -m scripts.make_model_card >> "$LOG" 2>&1
code=$?
log "model card exit $code"
status "DONE (model card exit $code). metrics.json now has a mismatch section; docs/MODEL_CARD.md was regenerated. Nothing was committed."
log "mismatch autopilot finished"
