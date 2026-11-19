"""Tests for Phase 4 cover preparation and reproducible stego datasets."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.steganalysis.deep.dataset import (
    FixedStegoDataset,
    StegoPairDataset,
    fixed_set_path,
    generate_fixed_stego_set,
)
from scripts.make_sample_data import create_sample_images
from scripts.prepare_dataset import main as prepare_main
from scripts.prepare_dataset import prepare_dataset


def _write_source_images(directory: Path, count: int = 30) -> list[Path]:
    """Create distinct lossless grayscale covers for dataset tests."""
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index in range(count):
        image = np.full((72, 80), index * 5 % 256, dtype=np.uint8)
        image[index % 72, index % 80] = 255
        path = directory / f"photo_{index:03d}.png"
        Image.fromarray(image).save(path)
        paths.append(path)
    return paths


def _write_midrange_covers(directory: Path, count: int = 3) -> list[Path]:
    """Create covers away from 0/255, where LSB matching may step either way.

    At 0 and 255 matching is forced to +1/-1 and never changes upper bits, so
    bit-plane tests need values in the middle of the range.
    """
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index in range(count):
        rows, columns = np.indices((72, 80))
        image = (100 + (rows + columns + index) % 50).astype(np.uint8)
        path = directory / f"mid_{index:03d}.png"
        Image.fromarray(image).save(path)
        paths.append(path)
    return paths


def _hash(path: Path) -> str:
    """Hash exact file bytes for deterministic output comparisons."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prepare_dataset_resizes_hashes_and_splits_by_cover_id(tmp_path: Path) -> None:
    """Thirty inputs yield expected grayscale output and disjoint seeded splits."""
    source = tmp_path / "source"
    output = tmp_path / "prepared"
    _write_source_images(source)
    card = prepare_dataset(source, output, size=48, seed=1337, origin="test photos")

    splits = json.loads((output / "splits.json").read_text(encoding="utf-8"))["splits"]
    split_ids = [cover_id for cover_ids in splits.values() for cover_id in cover_ids]
    assert len(split_ids) == 30
    assert len(set(split_ids)) == 30
    assert {name: len(ids) for name, ids in splits.items()} == {
        "train": 21,
        "val": 4,
        "test": 5,
    }
    assert card["origin"] == "test photos"
    assert card["image_count"] == 30
    assert card["splits"] == {"train": 21, "val": 4, "test": 5}
    for filename, digest in card["image_sha256"].items():
        output_path = output / filename
        assert _hash(output_path) == digest
        with Image.open(output_path) as image:
            assert image.mode == "L"
            assert image.size == (48, 48)


def test_prepare_dataset_is_reproducible_across_destinations(tmp_path: Path) -> None:
    """Same source and split seed produce identical split and image hashes."""
    source = tmp_path / "source"
    _write_source_images(source, count=11)
    first = prepare_dataset(source, tmp_path / "first", seed=99)
    second = prepare_dataset(source, tmp_path / "second", seed=99)
    assert first["image_sha256"] == second["image_sha256"]
    assert json.loads((tmp_path / "first" / "splits.json").read_text()) == json.loads(
        (tmp_path / "second" / "splits.json").read_text()
    )
    assert (tmp_path / "first" / "splits.json").read_bytes() == (
        tmp_path / "second" / "splits.json"
    ).read_bytes()
    with pytest.raises(ValueError, match="inside the source"):
        prepare_dataset(source, source / "prepared")


def test_prepare_dataset_cli_and_input_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The documented CLI runs and invalid source directories fail explicitly."""
    source = tmp_path / "source"
    output = tmp_path / "covers"
    _write_source_images(source, count=2)
    assert (
        prepare_main(
            [
                "--src",
                str(source),
                "--out",
                str(output),
                "--size",
                "32",
                "--seed",
                "7",
            ]
        )
        == 0
    )
    assert "Prepared 2 grayscale images" in capsys.readouterr().out
    with pytest.raises(FileNotFoundError):
        prepare_dataset(tmp_path / "missing", output)
    with pytest.raises(ValueError, match="positive"):
        prepare_dataset(source, output, size=0)
    empty_source = tmp_path / "empty-source"
    empty_source.mkdir()
    with pytest.raises(ValueError, match="No supported image"):
        prepare_dataset(empty_source, output / "empty")


def test_prepare_dataset_decodes_color_and_jpeg_sources(tmp_path: Path) -> None:
    """RGB JPEG source images are actually decoded and converted to grayscale."""
    source = tmp_path / "source"
    source.mkdir()
    color = Image.new("RGB", (40, 30), (100, 150, 200))
    color.save(source / "color.jpg", format="JPEG")
    output = tmp_path / "prepared"
    prepare_dataset(source, output, size=24)
    with Image.open(output / "cover_00000.png") as image:
        assert image.mode == "L"
        assert image.size == (24, 24)


def test_sample_collection_generator_creates_thirty_deterministic_images(
    tmp_path: Path,
) -> None:
    """Sample asset generator emits a compact, reproducible demo-only collection."""
    first = create_sample_images(tmp_path / "first", count=30, size=32)
    second = create_sample_images(tmp_path / "second", count=30, size=32)
    assert len(first) == len(second) == 30
    assert [_hash(path) for path in first] == [_hash(path) for path in second]
    with Image.open(first[0]) as image:
        assert image.mode == "L"
        assert image.size == (32, 32)
    with pytest.raises(ValueError, match="outside supported"):
        create_sample_images(tmp_path / "invalid", count=0)


def test_stego_pair_dataset_keeps_cover_and_stego_in_one_pair(tmp_path: Path) -> None:
    """On-the-fly samples have paired labels, normalized tensors, and seeded choices."""
    covers = _write_source_images(tmp_path / "covers", count=2)
    dataset = StegoPairDataset(covers, seed=55)
    first_images, first_labels = dataset[0]
    repeated_images, repeated_labels = dataset[0]
    assert len(dataset) == 2
    assert tuple(first_images.shape) == (2, 1, 72, 80)
    assert str(first_images.dtype) == "torch.float32"
    assert first_labels.tolist() == [0, 1]
    assert repeated_labels.tolist() == [0, 1]
    assert np.array_equal(first_images.numpy(), repeated_images.numpy())
    assert 0.0 <= float(first_images.min()) <= float(first_images.max()) <= 1.0
    dataset.set_epoch(1)
    next_epoch_images, _ = dataset[0]
    assert not np.array_equal(first_images.numpy(), next_epoch_images.numpy())
    dataset.set_epoch(2, payload_bpps=(0.4, 0.8))
    assert dataset.payload_bpps == (0.4, 0.8)
    dataset.set_epoch(3)
    assert dataset.payload_bpps == dataset.all_payload_bpps
    with pytest.raises(ValueError, match="at least one"):
        StegoPairDataset([], seed=1)
    with pytest.raises(ValueError, match="Seed"):
        StegoPairDataset(covers, seed=-1)
    with pytest.raises(ValueError, match="payload bpp"):
        dataset.set_epoch(4, payload_bpps=(0.9,))


def test_replace_only_training_never_touches_upper_bit_planes(tmp_path: Path) -> None:
    """The mismatch-experiment dataset must contain zero LSB-matching examples.

    LSB replacement only ever rewrites bit 0, so ``value >> 1`` is unchanged.
    LSB matching's ±1 steps (e.g. 2 -> 1) change upper bits on some samples,
    so this check would fail if any matching example slipped in.
    """
    covers = _write_midrange_covers(tmp_path / "covers")
    dataset = StegoPairDataset(covers, seed=7, methods=("lsb_replace",))
    for epoch in range(4):
        dataset.set_epoch(epoch)
        for index in range(len(dataset)):
            images, _ = dataset[index]
            cover, stego = (np.rint(images[i, 0].numpy() * 255).astype(np.uint8) for i in (0, 1))
            assert np.array_equal(cover >> 1, stego >> 1)
    with pytest.raises(ValueError, match="Training methods"):
        StegoPairDataset(covers, methods=())
    with pytest.raises(ValueError, match="Training methods"):
        StegoPairDataset(covers, methods=("lsb_flip",))  # type: ignore[arg-type]


def test_matching_mixture_does_change_upper_bit_planes(tmp_path: Path) -> None:
    """Sanity check for the test above: the default mixture includes matching."""
    covers = _write_midrange_covers(tmp_path / "covers")
    dataset = StegoPairDataset(covers, seed=7, methods=("lsb_match",))
    images, _ = dataset[0]
    cover, stego = (np.rint(images[i, 0].numpy() * 255).astype(np.uint8) for i in (0, 1))
    assert not np.array_equal(cover >> 1, stego >> 1)


@pytest.mark.parametrize("method", ["lsb_replace", "lsb_match"])
def test_fixed_dataset_regenerates_bit_identically_and_loads_pairs(
    tmp_path: Path,
    method: str,
) -> None:
    """Fixed validation/test examples regenerate exactly for either embed method."""
    covers = _write_source_images(tmp_path / "covers", count=3)
    first_path = fixed_set_path(tmp_path / "fixed", "val", method, "keyed", 0.1)
    second_path = tmp_path / "second"
    generate_fixed_stego_set(
        covers,
        first_path,
        payload_bpp=0.1,
        method=method,  # type: ignore[arg-type]
        seed=42,
    )
    generate_fixed_stego_set(
        covers,
        second_path,
        payload_bpp=0.1,
        method=method,  # type: ignore[arg-type]
        seed=42,
    )
    first_files = sorted(path.name for path in first_path.iterdir())
    second_files = sorted(path.name for path in second_path.iterdir())
    assert first_files == second_files
    assert {name: _hash(first_path / name) for name in first_files} == {
        name: _hash(second_path / name) for name in second_files
    }

    dataset = FixedStegoDataset(first_path)
    images, labels = dataset[0]
    assert len(dataset) == 3
    assert tuple(images.shape) == (2, 1, 72, 80)
    assert str(images.dtype) == "torch.float32"
    assert labels.tolist() == [0, 1]
    metadata = json.loads((first_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["source_cover_ids"] == [f"cover_{index:05d}" for index in range(3)]
    assert metadata["pairs"][0]["source_cover_sha256"]


def test_fixed_dataset_rejects_tampering_and_invalid_paths(tmp_path: Path) -> None:
    """Fixed set loading checks hashes and only accepts val/test directory names."""
    cover = _write_source_images(tmp_path / "covers", count=1)
    output = tmp_path / "fixed"
    generate_fixed_stego_set(cover, output, payload_bpp=0.1, seed=5)
    dataset = FixedStegoDataset(output)
    (output / "stego_00000.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        dataset[0]
    with pytest.raises(FileNotFoundError, match="metadata"):
        FixedStegoDataset(tmp_path / "missing")
    with pytest.raises(ValueError, match="val and test"):
        fixed_set_path(tmp_path, "train", "lsb_replace", "keyed", 0.1)
    assert fixed_set_path(tmp_path, "test", "lsb_replace", "keyed", 1.0).name.endswith("_1")
    with pytest.raises(ValueError, match="in \\(0, 1.0\\]"):
        fixed_set_path(tmp_path, "val", "lsb_replace", "keyed", 1.1)
    with pytest.raises(ValueError, match="At least one"):
        generate_fixed_stego_set([], output, payload_bpp=0.1)
