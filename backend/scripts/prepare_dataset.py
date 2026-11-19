"""Prepare lossless grayscale cover images and deterministic train/val/test splits."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import TypedDict

from PIL import Image, UnidentifiedImageError

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".pgm", ".png", ".tif", ".tiff", ".webp"}
DEFAULT_SIZE = 256
DEFAULT_SEED = 1337


class DatasetSplits(TypedDict):
    """Cover IDs partitioned into train, validation, and test groups."""

    seed: int
    splits: dict[str, list[str]]


def prepare_dataset(
    source: Path,
    output: Path,
    size: int = DEFAULT_SIZE,
    seed: int = DEFAULT_SEED,
    origin: str = "unspecified user-provided image collection",
) -> dict[str, object]:
    """Convert source images into grayscale PNGs and create seeded cover splits.

    Args:
        source: Directory containing source images.
        output: Destination directory for resized images and metadata.
        size: Square output edge length in pixels.
        seed: Seed for the cover-level split.
        origin: Human-readable source attribution recorded in dataset metadata.

    Returns:
        The dataset card written to ``dataset_card.json``.

    Raises:
        FileNotFoundError: If the source directory does not exist.
        ValueError: If the source, size, seed, or an input image is invalid.
    """
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")
    if size < 1:
        raise ValueError("Output size must be a positive integer.")
    if seed < 0:
        raise ValueError("Seed must be non-negative.")
    if output.resolve().is_relative_to(source.resolve()):
        raise ValueError("Output directory must not be inside the source directory.")
    source_files = sorted(
        (
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ),
        key=lambda path: path.relative_to(source).as_posix().casefold(),
    )
    if not source_files:
        raise ValueError(f"No supported image files found in {source}.")

    output.mkdir(parents=True, exist_ok=True)
    cover_ids: list[str] = []
    image_hashes: dict[str, str] = {}
    for index, input_path in enumerate(source_files):
        cover_id = f"cover_{index:05d}"
        output_path = output / f"{cover_id}.png"
        _convert_to_grayscale_png(input_path, output_path, size)
        cover_ids.append(cover_id)
        image_hashes[output_path.name] = _sha256_file(output_path)

    split_data = _make_splits(cover_ids, seed)
    splits_path = output / "splits.json"
    splits_path.write_text(
        json.dumps(split_data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dataset_card: dict[str, object] = {
        "format_version": 1,
        "origin": origin,
        "source_count": len(source_files),
        "image_count": len(cover_ids),
        "size": [size, size],
        "mode": "L",
        "seed": seed,
        "splits": {name: len(ids) for name, ids in split_data["splits"].items()},
        "image_sha256": image_hashes,
        "splits_sha256": _sha256_file(splits_path),
    }
    (output / "dataset_card.json").write_text(
        json.dumps(dataset_card, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return dataset_card


def _convert_to_grayscale_png(source: Path, destination: Path, size: int) -> None:
    """Decode, resize, and save one 8-bit grayscale image."""
    try:
        with Image.open(source) as image:
            image.load()
            grayscale = image.convert("L")
            resized = grayscale.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(destination, format="PNG", compress_level=6)
            with Image.open(destination) as check:
                if check.mode != "L" or check.size != (size, size):
                    raise RuntimeError(f"Dataset output validation failed for {destination}.")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Could not decode source image {source}: {exc}") from exc


def _make_splits(cover_ids: list[str], seed: int) -> DatasetSplits:
    """Assign each cover ID to exactly one deterministic split."""
    import numpy as np

    shuffled = np.asarray(cover_ids, dtype=object)[
        np.random.default_rng(seed).permutation(len(cover_ids))
    ]
    train_end = int(len(cover_ids) * 0.70)
    validation_end = train_end + int(len(cover_ids) * 0.15)
    return {
        "seed": seed,
        "splits": {
            "train": shuffled[:train_end].tolist(),
            "val": shuffled[train_end:validation_end].tolist(),
            "test": shuffled[validation_end:].tolist(),
        },
    }


def _sha256_file(path: Path) -> str:
    """Hash a file's exact bytes with SHA-256."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    """Build the documented dataset preparation CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path, help="Folder of source images.")
    parser.add_argument("--out", required=True, type=Path, help="Output covers folder.")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="Square resize edge.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Split RNG seed.")
    parser.add_argument(
        "--origin",
        default="unspecified user-provided image collection",
        help="Dataset source attribution to record in the card.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run dataset preparation and report errors to stderr."""
    args = build_parser().parse_args(argv)
    try:
        card = prepare_dataset(args.src, args.out, args.size, args.seed, args.origin)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Dataset preparation failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Prepared {card['image_count']} grayscale images at {args.out}; splits: {card['splits']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
