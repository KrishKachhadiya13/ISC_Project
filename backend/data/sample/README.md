# Synthetic demo covers

This directory contains 30 deterministic, procedurally generated 256×256
grayscale PNG images. They are provided only for smoke tests and interactive
demos; they are **not photographs** and must not be used to claim steganalysis
training or evaluation performance.

Regenerate them from `backend/` with:

```powershell
python -m scripts.make_sample_data --out data/sample --count 30 --size 256 --seed 1337
```

Convert them into a prepared cover set with:

```powershell
python -m scripts.prepare_dataset --src data/sample --out data/covers256 --size 256 --seed 1337 --origin "StegaGuard synthetic demo covers"
```
