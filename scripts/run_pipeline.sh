#!/usr/bin/env bash
# Unattended pipeline: train -> evaluate -> docs -> checks. It never commits or pushes.
#
# Launched detached so it survives the end of an interactive session:
#   bash scripts/run_pipeline.sh
# Progress:  backend/data/logs/pipeline.log      Summary: backend/data/logs/PIPELINE_STATUS.md
#
# It never commits, never pushes, and never deletes data.
# Every step logs its exit code; a failed training run stops the pipeline.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACK="$ROOT/backend"
LOGS="$BACK/data/logs"
PY="$BACK/.venv/Scripts/python"
STATUS="$LOGS/PIPELINE_STATUS.md"
mkdir -p "$LOGS"
cd "$BACK" || exit 1

# One BLAS thread per process: several workers each allocating 16 threads' worth of
# buffers ran this laptop out of memory earlier.
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

declare -a RESULTS=()
log() { echo "$(date '+%F %T') $*" | tee -a "$LOGS/pipeline.log"; }
note() { RESULTS+=("- $1"); }
write_status() {
  {
    echo "# Pipeline status"
    echo
    echo "Updated: $(date '+%F %T')"
    echo
    printf '%s\n' "${RESULTS[@]}"
    echo
    echo "Full log: backend/data/logs/pipeline.log"
  } > "$STATUS"
}
run() { # run <label> <command...>; records pass/fail, never aborts the script
  local label="$1"; shift
  log "START $label"
  "$@" >> "$LOGS/pipeline.log" 2>&1
  local code=$?
  log "END   $label (exit $code)"
  if [ $code -eq 0 ]; then note "PASS $label"; else note "FAIL $label (exit $code)"; fi
  write_status
  return $code
}

log "pipeline started"
note "Started $(date '+%F %T')"
write_status

# 1. Main CNN. If this fails there is nothing meaningful to evaluate.
run "train cnn_v1" "$PY" -u -W ignore -m scripts.train_cnn --dataset data/bossbase-prepared \
  --models-out models --results-out results --fixed-out data/cnn-fixed --device cuda \
  --num-workers 5 --fixed-workers 4
if [ ! -f models/cnn_v1.pt ] || [ ! -f results/cnn_metrics.json ]; then
  note "STOPPED: cnn_v1 artifacts are missing, so nothing further was run."
  write_status; exit 1
fi
grep -E "epoch [0-9]+/" "$LOGS/pipeline.log" | tail -3 | sed 's/^/    /' >> "$STATUS"

# 2. Evaluate everything and regenerate generated docs.
run "evaluate (metrics.json, plots, ensemble)" "$PY" -W ignore -m scripts.evaluate --fixed data/cnn-fixed --workers 4
run "model card" "$PY" -W ignore -m scripts.make_model_card
run "API docs" "$PY" -W ignore -m scripts.export_api_docs

# 3. Mismatch experiment (Section 8.2): replacement-only CNN, shorter schedule to fit the time budget.
run "train cnn_mismatch_replace (20 epochs)" "$PY" -u -W ignore -m scripts.train_cnn \
  --dataset data/bossbase-prepared --models-out models --results-out results --fixed-out data/cnn-fixed \
  --device cuda --num-workers 5 --fixed-workers 4 --epochs 20 \
  --train-methods lsb_replace --model-name cnn_mismatch_replace
if [ -f results/cnn_mismatch_replace_metrics.json ]; then
  run "re-evaluate with mismatch section" "$PY" -W ignore -m scripts.evaluate --fixed data/cnn-fixed --workers 4
  run "model card (with mismatch)" "$PY" -W ignore -m scripts.make_model_card
fi

# 4. Quality gates.
run "backend lint (ruff)" "$PY" -m ruff check .
run "backend types (mypy)" "$PY" -m mypy app/core app/steganalysis app/api app/main.py
run "backend tests" "$PY" -m pytest -m "not slow" -q -p no:warnings --cov=app/core --cov-fail-under=85
( cd "$ROOT/frontend" && run "frontend typecheck" npx tsc --noEmit )
( cd "$ROOT/frontend" && run "frontend tests" npm test --silent )
( cd "$ROOT/frontend" && run "frontend build" npm run build --silent )

# 5. No commit step: the owner decides what to commit and to which branch.
note "Results are left uncommitted in the working tree (by design)."

# 6. Docker build check last and non-fatal (needs Docker running and spare memory).
if docker info > /dev/null 2>&1; then
  run "docker compose build" docker compose build
else
  note "SKIPPED docker compose build (Docker daemon not running)."
fi

note "Finished $(date '+%F %T')"
write_status
log "pipeline finished"
