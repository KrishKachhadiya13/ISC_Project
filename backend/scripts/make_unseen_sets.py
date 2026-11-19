"""Build TEST sets for techniques the detectors were never trained on.

Run from ``backend/``::

    python -m scripts.make_unseen_sets --workers 3

It writes fixed, seeded cover/stego pairs under ``data/cnn-fixed/test/`` in the same
format as the training script's sets, so ``scripts.evaluate`` scores them unchanged:

* ``lsb2_replace_keyed_<bpp>``: real 2-LSB embedding (recoverable) on the full test split;
* ``suniward_sim_simulated_<bpp>`` and ``hill_sim_simulated_<bpp>``: adaptive-embedding
  simulations (see ``app/core/stego/simulate.py``) on a fixed subset of the test split,
  because each image costs about 0.25 s.

Only TEST sets are made. Validation data (used to fit the ensemble and thresholds) is not
touched, so adding these techniques cannot change how the detectors were tuned.

Existing sets are kept, so the script can be re-run safely. Worker processes import only
NumPy, SciPy and Pillow (never PyTorch), which keeps their memory small.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.stego.simulate import SIMULATED_METHODS, SchemeName, simulate_embedding  # noqa: E402

DEFAULT_PAYLOADS = (0.05, 0.1, 0.2, 0.4, 1.0)
FORMAT_VERSION = 1
BASE_SEED = 1337


def _condition_seed(name: str) -> int:
    """A stable per-set seed derived from the set name."""
    return BASE_SEED + int(hashlib.sha256(name.encode()).hexdigest(), 16) % 1_000_000


def _png_bytes(image: np.ndarray) -> bytes:
    """Encode a uint8 array as a metadata-free PNG."""
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format="PNG", compress_level=6)
    return buffer.getvalue()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.ascontiguousarray(np.asarray(image.convert("L"), dtype=np.uint8))


def make_simulated_set(job: dict[str, Any]) -> str:
    """Process-pool entry point: write one simulated set; returns its directory name."""
    directory = Path(job["directory"])
    scheme: SchemeName = job["scheme"]
    bpp: float = job["bpp"]
    seed = _condition_seed(directory.name)
    directory.mkdir(parents=True, exist_ok=True)
    pairs = []
    for index, (cover_id, cover_path) in enumerate(
        zip(job["cover_ids"], job["cover_paths"], strict=True)
    ):
        cover = _load_gray(Path(cover_path))
        stego = simulate_embedding(cover, bpp, scheme, seed=seed + index)
        cover_png, stego_png = _png_bytes(cover), _png_bytes(stego)
        (directory / f"cover_{index:05d}.png").write_bytes(cover_png)
        (directory / f"stego_{index:05d}.png").write_bytes(stego_png)
        pairs.append(
            {
                "cover": f"cover_{index:05d}.png",
                "stego": f"stego_{index:05d}.png",
                "cover_sha256": _sha256(cover_png),
                "stego_sha256": _sha256(stego_png),
                "cover_id": cover_id,
                "source_cover_sha256": _sha256(cover.tobytes()),
            }
        )
    metadata = {
        "format_version": FORMAT_VERSION,
        "seed": seed,
        "payload_bpp": bpp,
        "method": SIMULATED_METHODS[scheme],
        "mode": "simulated",
        "pairs": pairs,
        "source_cover_ids": list(job["cover_ids"]),
    }
    (directory / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return directory.name


def build_parser() -> argparse.ArgumentParser:
    """Command-line options."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", type=Path, default=Path("data/bossbase-prepared"))
    parser.add_argument("--fixed-out", type=Path, default=Path("data/cnn-fixed"))
    parser.add_argument(
        "--sim-covers", type=int, default=500, help="Test covers per simulated set."
    )
    parser.add_argument("--lsb2-covers", type=int, default=1500, help="Test covers per 2-LSB set.")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--payloads", type=float, nargs="+", default=list(DEFAULT_PAYLOADS))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Create every missing unseen-technique test set."""
    args = build_parser().parse_args(argv)
    splits = json.loads((args.dataset / "splits.json").read_text(encoding="utf-8"))["splits"]
    test_ids: list[str] = splits["test"]
    root = args.fixed_out / "test"

    # 1) Simulated adaptive schemes, in parallel light processes.
    jobs = []
    sim_ids = test_ids[: args.sim_covers]
    for scheme, method in SIMULATED_METHODS.items():
        for bpp in args.payloads:
            directory = root / f"{method}_simulated_{bpp:g}"
            if (directory / "metadata.json").is_file():
                continue
            jobs.append(
                {
                    "directory": str(directory),
                    "scheme": scheme,
                    "bpp": bpp,
                    "cover_ids": sim_ids,
                    "cover_paths": [str(args.dataset / f"{cid}.png") for cid in sim_ids],
                }
            )
    print(f"{len(jobs)} simulated sets to build ({len(sim_ids)} covers each)", flush=True)
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for name in pool.map(make_simulated_set, jobs):
            print("built", name, flush=True)

    # 2) Real 2-LSB embedding, reusing the training script's fixed-set generator (imports torch,
    #    so it runs here in the main process after the pool is finished).
    from app.steganalysis.deep.dataset import fixed_set_path, generate_fixed_stego_set

    lsb2_ids = test_ids[: args.lsb2_covers]
    for bpp in args.payloads:
        directory = fixed_set_path(args.fixed_out, "test", "lsb2_replace", "keyed", bpp)
        if (directory / "metadata.json").is_file():
            continue
        generate_fixed_stego_set(
            [args.dataset / f"{cid}.png" for cid in lsb2_ids],
            directory,
            payload_bpp=bpp,
            method="lsb2_replace",
            mode="keyed",
            seed=_condition_seed(directory.name),
            cover_ids=lsb2_ids,
        )
        print("built", directory.name, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
