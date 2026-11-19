"""On-the-fly paired training data and reproducible fixed stego datasets."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError
from torch import Tensor
from torch.utils.data import Dataset

from app.core.stego.embed import KEYED_SALT_BITS, EmbeddingMethod, EmbeddingMode, embed
from app.core.stego.header import HEADER_BITS
from app.core.stego.image_io import save_png

TRAINING_PAYLOAD_BPP = (0.05, 0.1, 0.2, 0.4, 0.8)
TRAINING_METHODS: tuple[EmbeddingMethod, ...] = ("lsb_replace", "lsb_match")
FIXED_FORMAT_VERSION = 1


class StegoPairDataset(Dataset[tuple[Tensor, Tensor]]):
    """Generate one cover/stego pair per item for pair-batched training.

    Each item returns images shaped ``(2, 1, H, W)`` and labels ``(0, 1)``.
    A normal DataLoader therefore keeps each cover and its stego partner in
    the same batch. ``set_epoch`` changes the deterministic per-item random
    choices between training epochs.
    """

    def __init__(
        self,
        cover_paths: Sequence[Path],
        seed: int = 1337,
        payload_bpps: Sequence[float] = TRAINING_PAYLOAD_BPP,
        methods: Sequence[EmbeddingMethod] = TRAINING_METHODS,
    ) -> None:
        """Store validated cover paths and stochastic training parameters.

        ``methods`` defaults to the blueprint's 50/50 replace/match mixture.
        Passing only ``("lsb_replace",)`` builds the mismatch experiment
        (Section 8.2), whose model never sees LSB matching during training.
        """
        self.cover_paths = tuple(Path(path) for path in cover_paths)
        if not self.cover_paths:
            raise ValueError("StegoPairDataset requires at least one cover image.")
        if seed < 0:
            raise ValueError("Seed must be non-negative.")
        if not payload_bpps or any(not 0 < bpp <= 0.8 for bpp in payload_bpps):
            raise ValueError("Training payload bpp values must be in (0, 0.8].")
        if not methods or any(method not in TRAINING_METHODS for method in methods):
            raise ValueError("Training methods must be a non-empty subset of the LSB methods.")
        self.methods = tuple(methods)
        self.seed = seed
        self.all_payload_bpps = tuple(float(bpp) for bpp in payload_bpps)
        self.payload_bpps = self.all_payload_bpps
        self.epoch = 0

    def __len__(self) -> int:
        """Return the number of cover images available for paired sampling."""
        return len(self.cover_paths)

    def set_epoch(self, epoch: int, payload_bpps: Sequence[float] | None = None) -> None:
        """Set the epoch and optional curriculum payloads for deterministic sampling."""
        if epoch < 0:
            raise ValueError("Epoch must be non-negative.")
        if payload_bpps is not None and (
            not payload_bpps or any(not 0 < bpp <= 0.8 for bpp in payload_bpps)
        ):
            raise ValueError("Training payload bpp values must be in (0, 0.8].")
        self.epoch = epoch
        self.payload_bpps = (
            tuple(float(bpp) for bpp in payload_bpps)
            if payload_bpps is not None
            else self.all_payload_bpps
        )

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        """Return a float32 cover/stego pair and its clean/stego labels."""
        cover = _load_grayscale(self.cover_paths[index])
        rng = np.random.default_rng(np.random.SeedSequence([self.seed, self.epoch, index]))
        payload_bpp = self.payload_bpps[int(rng.integers(0, len(self.payload_bpps)))]
        method = self.methods[int(rng.integers(0, len(self.methods)))]
        payload_size = _payload_size(payload_bpp, cover.shape, "keyed")
        payload = rng.bytes(payload_size)
        # A random per-image key replaces the Argon2id step (about 95% of the
        # cost of making one training example); see expand_stego_key.
        stego_key = rng.bytes(32)
        stego = embed(
            cover,
            payload,
            method=method,
            mode="keyed",
            stego_key=stego_key,
            stego_salt=rng.bytes(16),
            matching_randomness=rng.bytes(cover.size),
        )
        images = torch.stack((_to_tensor(cover), _to_tensor(stego)))
        labels = torch.tensor((0, 1), dtype=torch.long)
        return images, labels


class FixedStegoDataset(Dataset[tuple[Tensor, Tensor]]):
    """Load immutable, hash-checked cover/stego pairs from a fixed-set folder."""

    def __init__(self, directory: Path) -> None:
        """Read a fixed set's JSON manifest and validate its pair records."""
        self.directory = Path(directory)
        metadata_path = self.directory / "metadata.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Fixed dataset metadata not found: {metadata_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("format_version") != FIXED_FORMAT_VERSION:
            raise ValueError("Unsupported fixed dataset format version.")
        pairs = metadata.get("pairs")
        if not isinstance(pairs, list):
            raise ValueError("Fixed dataset metadata must contain a pair list.")
        self.pairs: list[dict[str, str]] = []
        for pair in pairs:
            if not isinstance(pair, dict) or not all(
                isinstance(pair.get(field), str)
                for field in ("cover", "stego", "cover_sha256", "stego_sha256")
            ):
                raise ValueError("Invalid fixed dataset pair metadata.")
            if any(Path(pair[field]).name != pair[field] for field in ("cover", "stego")):
                raise ValueError("Fixed dataset image names must not contain directory paths.")
            self.pairs.append(pair)

    def __len__(self) -> int:
        """Return the number of cover/stego pairs."""
        return len(self.pairs)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        """Load and hash-check one clean/stego pair."""
        pair = self.pairs[index]
        _verify_hash(self.directory / pair["cover"], pair["cover_sha256"])
        _verify_hash(self.directory / pair["stego"], pair["stego_sha256"])
        cover = _load_grayscale(self.directory / pair["cover"])
        stego = _load_grayscale(self.directory / pair["stego"])
        images = torch.stack((_to_tensor(cover), _to_tensor(stego)))
        labels = torch.tensor((0, 1), dtype=torch.long)
        return images, labels


def generate_fixed_stego_set(
    cover_paths: Sequence[Path],
    output_directory: Path,
    *,
    payload_bpp: float,
    method: EmbeddingMethod = "lsb_replace",
    mode: EmbeddingMode = "keyed",
    seed: int = 1337,
    cover_ids: Sequence[str] | None = None,
) -> Path:
    """Generate a deterministic fixed set and return its output directory.

    Offline-only fixed salts, passphrases, and LSB-matching coin bytes are
    derived from the supplied seed. They make evaluation examples repeatable;
    they must never be reused for live communication.
    """
    if not cover_paths:
        raise ValueError("At least one cover image is required.")
    if not 0 < payload_bpp <= 1.0:
        raise ValueError("Fixed payload bpp must be in (0, 1.0].")
    if seed < 0:
        raise ValueError("Seed must be non-negative.")
    if cover_ids is not None and (
        len(cover_ids) != len(cover_paths)
        or any(not cover_id or Path(cover_id).name != cover_id for cover_id in cover_ids)
        or len(set(cover_ids)) != len(cover_ids)
    ):
        raise ValueError("Cover IDs must be unique safe names matching the cover paths.")
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    pair_records: list[dict[str, str]] = []

    for index, cover_path in enumerate(cover_paths):
        cover = _load_grayscale(Path(cover_path))
        rng = np.random.default_rng(np.random.SeedSequence([seed, index]))
        payload_size = _payload_size(payload_bpp, cover.shape, mode)
        payload = rng.bytes(payload_size)
        stego = embed(
            cover,
            payload,
            method=method,
            mode=mode,
            stego_passphrase=rng.bytes(32).hex() if mode == "keyed" else None,
            stego_salt=rng.bytes(16) if mode == "keyed" else None,
            matching_randomness=rng.bytes(cover.size),
        )
        cover_name = f"cover_{index:05d}.png"
        stego_name = f"stego_{index:05d}.png"
        cover_path_out = output_directory / cover_name
        stego_path_out = output_directory / stego_name
        cover_path_out.write_bytes(save_png(cover))
        stego_path_out.write_bytes(save_png(stego))
        pair_records.append(
            {
                "cover": cover_name,
                "stego": stego_name,
                "cover_sha256": _sha256_file(cover_path_out),
                "stego_sha256": _sha256_file(stego_path_out),
                "cover_id": cover_ids[index] if cover_ids is not None else f"cover_{index:05d}",
                "source_cover_sha256": hashlib.sha256(cover.tobytes()).hexdigest(),
            }
        )

    metadata: dict[str, Any] = {
        "format_version": FIXED_FORMAT_VERSION,
        "seed": seed,
        "payload_bpp": payload_bpp,
        "method": method,
        "mode": mode,
        "pairs": pair_records,
        "source_cover_ids": list(cover_ids)
        if cover_ids is not None
        else [f"cover_{index:05d}" for index in range(len(cover_paths))],
    }
    (output_directory / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_directory


def fixed_set_path(
    root: Path,
    split: str,
    method: EmbeddingMethod,
    mode: EmbeddingMode,
    payload_bpp: float,
) -> Path:
    """Build the blueprint's canonical fixed-set directory path."""
    if split not in {"val", "test"}:
        raise ValueError("Fixed stego sets are only for the val and test splits.")
    if not 0 < payload_bpp <= 1.0:
        raise ValueError("Fixed payload bpp must be in (0, 1.0].")
    return Path(root) / split / f"{method}_{mode}_{payload_bpp:g}"


def _load_grayscale(path: Path) -> NDArray[np.uint8]:
    """Decode one image and return a contiguous 8-bit grayscale array."""
    try:
        with Image.open(path) as image:
            image.load()
            return np.ascontiguousarray(np.asarray(image.convert("L"), dtype=np.uint8))
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Could not decode cover image {path}: {exc}") from exc


def _payload_size(payload_bpp: float, shape: tuple[int, ...], mode: EmbeddingMode) -> int:
    """Choose whole payload bytes so total embedded bits approximate requested bpp."""
    header_and_salt = HEADER_BITS + (KEYED_SALT_BITS if mode == "keyed" else 0)
    desired_bits = math.floor(payload_bpp * shape[0] * shape[1])
    payload_bytes = (desired_bits - header_and_salt) // 8
    if payload_bytes < 1:
        raise ValueError(
            "Cover image is too small to represent the requested payload bpp after framing."
        )
    return payload_bytes


def _to_tensor(image: NDArray[np.uint8]) -> Tensor:
    """Convert grayscale uint8 samples to normalized ``(1, H, W)`` float32."""
    return torch.from_numpy(image.copy()).unsqueeze(0).to(torch.float32).div_(255.0)


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 over an exact image file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_hash(path: Path, expected: str) -> None:
    """Reject mutated fixed images instead of silently evaluating changed data."""
    actual = _sha256_file(path)
    if actual != expected:
        raise ValueError(f"Fixed dataset image hash mismatch: {path.name}")
