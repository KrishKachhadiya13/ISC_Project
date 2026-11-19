"""Copy a few held-out BOSSbase test covers into the frontend's demo folder.

Run from ``backend/``::

    python -m scripts.make_demo_assets

Why: the detectors were trained on BOSSbase-style images. A tiny JPEG-origin
photo (the CC0 fixture bundled for the crypto demo) is a *different* kind of
image, and the classical model flags even its clean version. For the
detection parts of a demo, use covers from the same distribution.

The images come from the **test** split (never seen in training) and are
written to ``frontend/public/demo/`` where ``.gitignore`` keeps them out of the
repository: BOSSbase is not redistributed here.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEMO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo"


def build_parser() -> argparse.ArgumentParser:
    """Command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/bossbase-prepared"))
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--out", type=Path, default=DEMO_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Copy the first ``count`` test-split covers (split order is already seeded)."""
    args = build_parser().parse_args(argv)
    splits_path = args.dataset / "splits.json"
    if not splits_path.is_file():
        print(f"No splits.json in {args.dataset}; run `make dataset` first.", file=sys.stderr)
        return 1
    splits = json.loads(splits_path.read_text(encoding="utf-8"))
    test_ids: list[str] = splits["splits"]["test"][: args.count]
    args.out.mkdir(parents=True, exist_ok=True)
    for index, cover_id in enumerate(test_ids, start=1):
        source = args.dataset / f"{cover_id}.png"
        target = args.out / f"bossbase_{index:02d}.png"
        shutil.copyfile(source, target)
        print(f"{source.name} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
