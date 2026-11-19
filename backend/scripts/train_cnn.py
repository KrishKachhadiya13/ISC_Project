"""Train and evaluate StegNet-Lite on a prepared, cover-disjoint image dataset."""

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from pathlib import Path
from typing import TypeAlias

import matplotlib
import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError
from torch import Tensor
from torch.utils.data import ConcatDataset, DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.stego.embed import EmbeddingMethod, EmbeddingMode
from app.steganalysis.deep.dataset import (
    FixedStegoDataset,
    StegoPairDataset,
    fixed_set_path,
    generate_fixed_stego_set,
)
from app.steganalysis.deep.model import build_model
from app.steganalysis.deep.train import (
    TrainingConfig,
    TrainingResult,
    calculate_metrics,
    evaluate_logits,
    plot_training_curves,
    save_checkpoint,
    train_model,
)

matplotlib.use("Agg")

PayloadGrid: TypeAlias = tuple[float, ...]
MethodGrid: TypeAlias = tuple[EmbeddingMethod, ...]
ModeGrid: TypeAlias = tuple[EmbeddingMode, ...]
DEFAULT_SEED = 1337
DEFAULT_PAYLOADS: PayloadGrid = (0.05, 0.1, 0.2, 0.4, 1.0)
DEFAULT_METHODS: MethodGrid = ("lsb_replace", "lsb_match")
DEFAULT_MODES: ModeGrid = ("keyed", "sequential")
DEFAULT_MODEL_NAME = "cnn_v1"
MODEL_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,40}$")


def output_file_names(model_name: str) -> dict[str, str]:
    """Return checkpoint, metadata, metrics, and curve filenames for one run.

    The default model keeps its original ``cnn_metrics.json`` and
    ``cnn_training_curves.png`` names so existing notebooks and docs stay
    valid; any other run gets files prefixed with its own name.
    """
    prefix = "cnn" if model_name == DEFAULT_MODEL_NAME else model_name
    return {
        "checkpoint": f"{model_name}.pt",
        "intermediate": f"{model_name}_best.tmp.pt",
        "metadata": f"{model_name}.json",
        "metrics": f"{prefix}_metrics.json",
        "curves": f"{prefix}_training_curves.png",
    }


def build_parser() -> argparse.ArgumentParser:
    """Create the CNN training command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", required=True, type=Path, help="Prepared grayscale cover directory."
    )
    parser.add_argument("--models-out", type=Path, default=Path("models"))
    parser.add_argument("--results-out", type=Path, default=Path("results"))
    parser.add_argument("--fixed-out", type=Path, default=Path("data/cnn-fixed"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--batch-pairs", type=int, default=32)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument(
        "--fixed-workers",
        type=int,
        default=1,
        help="Processes for generating fixed val/test sets (contents are identical either way).",
    )
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--truncation", type=float, default=3.0)
    parser.add_argument("--payloads", type=_parse_payloads, default=DEFAULT_PAYLOADS)
    parser.add_argument(
        "--methods",
        type=_parse_methods,
        default=DEFAULT_METHODS,
        help="Methods in the fixed validation/test grid (what the model is evaluated on).",
    )
    parser.add_argument(
        "--train-methods",
        type=_parse_methods,
        default=DEFAULT_METHODS,
        help="Methods used to generate training stego (lsb_replace alone = mismatch experiment).",
    )
    parser.add_argument(
        "--model-name",
        type=_parse_model_name,
        default=DEFAULT_MODEL_NAME,
        help="Output name; non-default names keep a second run from overwriting cnn_v1.",
    )
    parser.add_argument("--modes", type=_parse_modes, default=DEFAULT_MODES)
    parser.add_argument("--max-covers-per-split", type=int)
    parser.add_argument("--max-total-covers", type=int)
    parser.add_argument("--bootstrap-resamples", type=int, default=1000)
    parser.add_argument("--latency-samples", type=int, default=32)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Train on the train split, select/calibrate on val, and evaluate fixed test sets."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    try:
        if args.seed < 0:
            raise ValueError("Seed must be non-negative.")
        if args.bootstrap_resamples < 0 or args.latency_samples < 1:
            raise ValueError(
                "Bootstrap count must be non-negative and latency sample count positive."
            )
        if args.max_covers_per_split is not None and args.max_covers_per_split < 2:
            raise ValueError("At least two covers per split are required.")
        if args.max_total_covers is not None and args.max_total_covers < 6:
            raise ValueError("At least six total covers are required for non-empty splits.")
        if args.max_total_covers is not None and args.max_covers_per_split is not None:
            raise ValueError("Use only one of --max-total-covers or --max-covers-per-split.")
        device = _choose_device(args.device)
        splits, dataset_origin = _load_splits(
            args.dataset,
            args.max_covers_per_split,
            args.max_total_covers,
        )
        training_hash = _hash_training_data(args.dataset, splits["train"])
        split_hash = hashlib.sha256((args.dataset / "splits.json").read_bytes()).hexdigest()

        fixed_sets = _prepare_fixed_sets(
            args.dataset,
            args.fixed_out,
            splits,
            args.payloads,
            args.methods,
            args.modes,
            args.seed,
            args.fixed_workers,
        )
        selection_method = "lsb_replace" if "lsb_replace" in args.methods else args.methods[0]
        selection_mode = "keyed" if "keyed" in args.modes else args.modes[0]
        selection_payload = min(args.payloads, key=lambda value: abs(value - 0.4))
        selection_key = (selection_method, selection_mode, selection_payload)
        selection_conditions = _selection_conditions(fixed_sets)
        validation_dataset = ConcatDataset(
            [FixedStegoDataset(fixed_sets[("val", *key)]) for key in selection_conditions]
        )
        validation_loader = _fixed_loader(validation_dataset, args.batch_pairs, args.num_workers)

        train_paths = [args.dataset / f"{cover_id}.png" for cover_id in splits["train"]]
        names = output_file_names(args.model_name)
        training_dataset = StegoPairDataset(train_paths, seed=args.seed, methods=args.train_methods)
        config = TrainingConfig(
            seed=args.seed,
            epochs=args.epochs,
            batch_pairs=args.batch_pairs,
            patience=args.patience,
            truncation=args.truncation,
            num_workers=args.num_workers,
            learning_rate=args.learning_rate,
        )
        model = build_model(args.truncation)
        intermediate_checkpoint = args.models_out / names["intermediate"]
        training_result = train_model(
            model,
            training_dataset,
            validation_loader,
            intermediate_checkpoint,
            config,
            device,
            validation_groups=[
                (f"{key[0].removeprefix('lsb_')}_{key[2]:g}", 2 * len(dataset))
                for key, dataset in zip(
                    selection_conditions, validation_dataset.datasets, strict=True
                )
            ],
        )
        intermediate_checkpoint.unlink(missing_ok=True)

        args.models_out.mkdir(parents=True, exist_ok=True)
        args.results_out.mkdir(parents=True, exist_ok=True)
        plots_dir = args.results_out / "plots"
        plot_training_curves(training_result.history, plots_dir / names["curves"])
        validation_logits, validation_labels, _ = evaluate_logits(
            training_result.model,
            validation_loader,
            device,
        )
        validation_metrics = calculate_metrics(
            validation_labels,
            validation_logits,
            temperature=training_result.temperature,
            threshold=training_result.validation_threshold,
            bootstrap_resamples=0,
            seed=args.seed,
        )
        fixed_test_metrics = _evaluate_fixed_test_sets(
            training_result,
            fixed_sets,
            args.payloads,
            args.methods,
            args.modes,
            args.batch_pairs,
            args.num_workers,
            args.bootstrap_resamples,
            args.seed,
            device,
        )
        cpu_latency = _measure_cpu_latency(
            training_result.model,
            fixed_sets[("test", *selection_key)],
            args.latency_samples,
        )
        training_time = training_result.elapsed_seconds
        hyperparameters: dict[str, object] = {
            "architecture": "StegNet-Lite",
            "epochs_requested": args.epochs,
            "epochs_completed": len(training_result.history),
            "best_epoch": training_result.best_epoch,
            "batch_pairs": args.batch_pairs,
            "learning_rate": config.learning_rate,
            "weight_decay": config.weight_decay,
            "gradient_clip": config.gradient_clip,
            "early_stopping_patience": args.patience,
            "curriculum": {
                "epochs_1_to_8_bpp": [0.4, 0.8],
                "later_epochs_bpp": [0.05, 0.1, 0.2, 0.4, 0.8],
            },
            "training_methods": list(args.train_methods),
            "training_mode": "keyed",
            "truncation": args.truncation,
            "device": str(device),
            "seed": args.seed,
            "payloads_tested": list(args.payloads),
            "methods_tested": list(args.methods),
            "modes_tested": list(args.modes),
        }
        metadata: dict[str, object] = {
            "format_version": 1,
            "model": args.model_name,
            "dataset_origin": dataset_origin,
            "training_data_sha256": training_hash,
            "dataset_split_sha256": split_hash,
            "git_commit_hash": _git_commit_hash(args.dataset),
            "seed": args.seed,
            "temperature": training_result.temperature,
            "validation_selection": {
                "conditions": [
                    {"method": key[0], "mode": key[1], "payload_bpp": key[2]}
                    for key in selection_conditions
                ],
                "roc_auc": training_result.best_validation_auc,
                "p_e": training_result.best_validation_pe,
                "threshold": training_result.validation_threshold,
                "calibrated_metrics": validation_metrics,
            },
            "training_time_seconds": training_time,
            "trainable_parameter_count": training_result.model.trainable_parameter_count(),
            "hyperparameters": hyperparameters,
            "split_counts": {name: len(ids) for name, ids in splits.items()},
            "limitations": [
                "Model was trained on grayscale keyed LSB steganography using "
                + ", ".join(args.train_methods)
                + " only.",
                "RGB inference scores channels independently and is not RGB-trained.",
                "Heatmaps indicate model response and are not proof of hidden data.",
            ],
        }
        checkpoint_path = args.models_out / names["checkpoint"]
        save_checkpoint(
            training_result.model,
            checkpoint_path,
            temperature=training_result.temperature,
            metadata=metadata,
        )
        (args.models_out / names["metadata"]).write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        results: dict[str, object] = {
            "format_version": 1,
            "model": args.model_name,
            "training_methods": list(args.train_methods),
            "dataset_origin": dataset_origin,
            "training_data_sha256": training_hash,
            "dataset_split_sha256": split_hash,
            "seed": args.seed,
            "training_time_seconds": training_time,
            "cpu_inference_latency_ms_per_image": cpu_latency,
            "validation_selection": metadata["validation_selection"],
            "splits": {
                name: {"cover_count": len(ids), "cover_ids": ids} for name, ids in splits.items()
            },
            "test_evaluations": fixed_test_metrics,
            "smoke_subset": (
                args.max_covers_per_split is not None or args.max_total_covers is not None
            ),
        }
        results_path = args.results_out / names["metrics"]
        results_path.write_text(
            json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"CNN training failed: {exc}", file=sys.stderr)
        return 1

    names = output_file_names(args.model_name)
    print(f"Saved CNN checkpoint to {args.models_out / names['checkpoint']}")
    print(f"Saved CNN metadata to {args.models_out / names['metadata']}")
    print(f"Saved metrics to {args.results_out / names['metrics']}")
    print(f"Saved training curves to {args.results_out / 'plots' / names['curves']}")
    if args.max_covers_per_split is not None or args.max_total_covers is not None:
        print("WARNING: capped smoke run; these metrics are not benchmark results.")
    return 0


def _prepare_fixed_sets(
    dataset_dir: Path,
    fixed_root: Path,
    splits: dict[str, list[str]],
    payloads: PayloadGrid,
    methods: MethodGrid,
    modes: ModeGrid,
    seed: int,
    fixed_workers: int = 1,
) -> dict[tuple[str, str, str, float], Path]:
    """Create or validate deterministic fixed validation and test conditions.

    Missing sets are generated in parallel processes. This cannot change
    their contents: each set derives every random choice from its own
    condition seed, so the result is identical in any order.
    """
    output: dict[tuple[str, str, str, float], Path] = {}
    pending: list[dict[str, object]] = []
    for split_name in ("val", "test"):
        cover_ids = splits[split_name]
        cover_paths = [dataset_dir / f"{cover_id}.png" for cover_id in cover_ids]
        for method in methods:
            for mode in modes:
                for payload_bpp in payloads:
                    condition_seed = _condition_seed(seed, split_name, method, mode, payload_bpp)
                    path = fixed_set_path(fixed_root, split_name, method, mode, payload_bpp)
                    if (path / "metadata.json").is_file():
                        _validate_existing_fixed_set(
                            dataset_dir,
                            path,
                            cover_ids,
                            method,
                            mode,
                            payload_bpp,
                            condition_seed,
                        )
                    else:
                        pending.append(
                            {
                                "cover_paths": cover_paths,
                                "output_directory": path,
                                "payload_bpp": payload_bpp,
                                "method": method,
                                "mode": mode,
                                "seed": condition_seed,
                                "cover_ids": cover_ids,
                            }
                        )
                    output[(split_name, method, mode, payload_bpp)] = path
    _generate_pending_sets(pending, fixed_workers)
    return output


def _generate_pending_sets(pending: list[dict[str, object]], workers: int) -> None:
    """Generate missing fixed sets, in parallel when more than one worker is allowed."""
    if workers <= 1 or len(pending) <= 1:
        for job in pending:
            _generate_one_set(job)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        # list() re-raises the first worker exception, if any.
        list(pool.map(_generate_one_set, pending))


def _generate_one_set(job: dict[str, object]) -> Path:
    """Process-pool entry point: generate one fixed set from keyword arguments."""
    cover_paths = job.pop("cover_paths")
    output_directory = job.pop("output_directory")
    return generate_fixed_stego_set(cover_paths, output_directory, **job)  # type: ignore[arg-type]


def _validate_existing_fixed_set(
    dataset_dir: Path,
    directory: Path,
    cover_ids: list[str],
    method: EmbeddingMethod,
    mode: EmbeddingMode,
    payload_bpp: float,
    seed: int,
) -> None:
    """Refuse to reuse a fixed set generated from a different experiment."""
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    expected = {
        "source_cover_ids": cover_ids,
        "method": method,
        "mode": mode,
        "payload_bpp": payload_bpp,
        "seed": seed,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError(
            f"Existing fixed set metadata does not match the requested run: {directory}"
        )
    dataset = FixedStegoDataset(directory)
    if len(dataset) != len(cover_ids):
        raise ValueError(f"Existing fixed set has the wrong number of pairs: {directory}")
    for index, cover_id in enumerate(cover_ids):
        record = dataset.pairs[index]
        if record.get("cover_id") != cover_id:
            raise ValueError(
                f"Existing fixed set cover order does not match {cover_id}: {directory}"
            )
        if record.get("source_cover_sha256") != _source_cover_hash(dataset_dir / f"{cover_id}.png"):
            raise ValueError(f"Existing fixed set cover does not match {cover_id}: {directory}")


@cache
def _source_cover_hash(path: Path) -> str:
    """SHA-256 of a cover's pixels, cached because all 20 conditions of a split share covers."""
    return hashlib.sha256(_load_grayscale(path).tobytes()).hexdigest()


def _evaluate_fixed_test_sets(
    result: TrainingResult,
    fixed_sets: dict[tuple[str, str, str, float], Path],
    payloads: PayloadGrid,
    methods: MethodGrid,
    modes: ModeGrid,
    batch_pairs: int,
    num_workers: int,
    bootstrap_resamples: int,
    seed: int,
    device: torch.device,
) -> dict[str, object]:
    """Evaluate every method/mode/payload condition on held-out fixed test covers."""
    evaluations: dict[str, object] = {}
    for method_index, method in enumerate(methods):
        for mode_index, mode in enumerate(modes):
            for payload_index, payload_bpp in enumerate(payloads):
                directory = fixed_sets[("test", method, mode, payload_bpp)]
                dataset = FixedStegoDataset(directory)
                loader = _fixed_loader(dataset, batch_pairs, num_workers)
                logits, labels, _ = evaluate_logits(result.model, loader, device)
                evaluations[f"{method}|{mode}|{payload_bpp:g}"] = {
                    "method": method,
                    "mode": mode,
                    "payload_bits_per_pixel": payload_bpp,
                    "cover_level_split": "test",
                    **calculate_metrics(
                        labels,
                        logits,
                        temperature=result.temperature,
                        threshold=result.validation_threshold,
                        bootstrap_resamples=bootstrap_resamples,
                        seed=seed + method_index * 100 + mode_index * 10 + payload_index,
                    ),
                }
    return evaluations


def _measure_cpu_latency(model: torch.nn.Module, fixed_directory: Path, sample_count: int) -> float:
    """Measure mean CPU forward latency using a bounded number of fixed images."""
    dataset = FixedStegoDataset(fixed_directory)
    cpu_model = model.to("cpu").eval()
    samples: list[Tensor] = []
    for index in range(min(len(dataset), (sample_count + 1) // 2)):
        images, _ = dataset[index]
        samples.extend((images[0], images[1]))
        if len(samples) >= sample_count:
            break
    if not samples:
        raise ValueError("Cannot measure latency without test images.")
    warmup = samples[: min(2, len(samples))]
    with torch.inference_mode():
        for image in warmup:
            cpu_model(image.unsqueeze(0))
        started = time.perf_counter()
        for image in samples:
            cpu_model(image.unsqueeze(0))
    return (time.perf_counter() - started) * 1000 / len(samples)


def _load_splits(
    dataset_dir: Path,
    max_covers_per_split: int | None,
    max_total_covers: int | None,
) -> tuple[dict[str, list[str]], str]:
    """Load prepared dataset IDs and enforce a disjoint 256×256 split."""
    split_path = dataset_dir / "splits.json"
    card_path = dataset_dir / "dataset_card.json"
    if not split_path.is_file():
        raise FileNotFoundError(f"Missing prepared split metadata: {split_path}")
    if not card_path.is_file():
        raise FileNotFoundError(f"Missing prepared dataset card: {card_path}")
    split_data = json.loads(split_path.read_text(encoding="utf-8"))
    raw_splits = split_data.get("splits")
    if not isinstance(raw_splits, dict) or set(raw_splits) != {"train", "val", "test"}:
        raise ValueError("splits.json must contain train, val, and test cover lists.")
    splits: dict[str, list[str]] = {}
    for name in ("train", "val", "test"):
        values = raw_splits[name]
        if not isinstance(values, list) or not values:
            raise ValueError(f"The {name} split must contain cover IDs.")
        if any(
            not isinstance(value, str) or re.fullmatch(r"cover_\d{5}", value) is None
            for value in values
        ):
            raise ValueError("Cover IDs must use the prepared format 'cover_00000'.")
        splits[name] = values[:max_covers_per_split] if max_covers_per_split else values
        if len(splits[name]) < 2:
            raise ValueError("Each split must contain at least two covers.")
    if max_total_covers is not None:
        capacities = {name: len(splits[name]) for name in ("train", "val", "test")}
        if sum(capacities.values()) < max_total_covers:
            raise ValueError("Requested smoke subset exceeds the available cover count.")
        desired = {
            "train": int(max_total_covers * 0.70),
            "val": int(max_total_covers * 0.15),
        }
        desired["test"] = max_total_covers - desired["train"] - desired["val"]
        if min(desired.values()) < 2:
            raise ValueError("Total cover count must allocate at least two covers to every split.")
        if any(desired[name] > capacities[name] for name in desired):
            raise ValueError("The available splits cannot provide the requested 70/15/15 subset.")
        splits = {name: splits[name][: desired[name]] for name in ("train", "val", "test")}
    selected_ids = [cover_id for values in splits.values() for cover_id in values]
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Train, validation, and test covers must be disjoint.")
    for cover_id in selected_ids:
        image_path = dataset_dir / f"{cover_id}.png"
        image = _load_grayscale(image_path)
        if image.shape != (256, 256):
            raise ValueError(f"CNN training requires 256×256 prepared covers: {image_path}")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    origin = card.get("origin")
    if not isinstance(origin, str) or not origin.strip():
        raise ValueError("Dataset card must include a non-empty dataset origin.")
    return splits, origin


def _load_grayscale(path: Path) -> NDArray[np.uint8]:
    """Decode one prepared grayscale image without silent channel conversion."""
    try:
        with Image.open(path) as image:
            image.load()
            if image.mode != "L":
                raise ValueError(f"Prepared CNN cover must be grayscale: {path}")
            return np.asarray(image, dtype=np.uint8).copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Could not decode prepared CNN cover {path}: {exc}") from exc


def _hash_training_data(dataset_dir: Path, training_ids: list[str]) -> str:
    """Hash the exact training cover bytes and IDs in deterministic order."""
    digest = hashlib.sha256()
    for cover_id in sorted(training_ids):
        digest.update(cover_id.encode("utf-8"))
        digest.update((dataset_dir / f"{cover_id}.png").read_bytes())
    return digest.hexdigest()


def _condition_seed(seed: int, split: str, method: str, mode: str, payload_bpp: float) -> int:
    """Derive a deterministic but condition-specific seed for fixed embedding."""
    token = f"{seed}|{split}|{method}|{mode}|{payload_bpp:.8g}".encode()
    return int.from_bytes(hashlib.sha256(token).digest()[:4], "big")


# Checkpoint selection pools several validation conditions, from hard to easy,
# for both embedding methods. A single easy condition (such as replacement at
# 0.4 bpp) saturates early and would pick an epoch that has never seen the low
# payloads the project cares about.
SELECTION_CANDIDATES: tuple[tuple[str, str, float], ...] = (
    ("lsb_replace", "keyed", 0.1),
    ("lsb_replace", "keyed", 0.4),
    ("lsb_match", "keyed", 0.2),
    ("lsb_match", "keyed", 0.4),
)


def _selection_conditions(
    fixed_sets: dict[tuple[str, str, str, float], Path],
) -> list[tuple[str, str, float]]:
    """Validation conditions used for checkpoint selection, limited to those generated."""
    chosen = [key for key in SELECTION_CANDIDATES if ("val", *key) in fixed_sets]
    if chosen:
        return chosen
    # A reduced grid (smoke runs) may not contain the usual conditions.
    fallback = next(key[1:] for key in fixed_sets if key[0] == "val")
    return [fallback]


def _fixed_loader(
    dataset: FixedStegoDataset,
    batch_pairs: int,
    num_workers: int,
) -> DataLoader[tuple[Tensor, Tensor]]:
    """Build a deterministic pair-preserving loader for validation or test."""
    return DataLoader(
        dataset,
        batch_size=batch_pairs,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )


def _choose_device(requested: str) -> torch.device:
    """Resolve auto/cpu/cuda and fail clearly for unavailable requested CUDA."""
    if requested == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA was requested but no CUDA-enabled PyTorch device is available.")
    if requested == "auto":
        requested = "cuda" if torch.cuda.is_available() else "cpu"
    return torch.device(requested)


def _git_commit_hash(start_path: Path) -> str | None:
    """Return repository HEAD if available, without requiring Git in cloud archives."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=start_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _parse_payloads(value: str) -> PayloadGrid:
    """Parse and validate a comma-separated payload grid."""
    try:
        payloads = tuple(float(part) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Payloads must be comma-separated numbers.") from exc
    if not payloads or any(not 0 < bpp <= 1.0 for bpp in payloads):
        raise argparse.ArgumentTypeError("Payloads must be greater than 0 and at most 1.0 bpp.")
    return payloads


def _parse_methods(value: str) -> MethodGrid:
    """Parse supported LSB embedding method names."""
    methods = tuple(value.split(","))
    if not methods or any(method not in DEFAULT_METHODS for method in methods):
        raise argparse.ArgumentTypeError("Methods must be lsb_replace and/or lsb_match.")
    return methods  # type: ignore[return-value]


def _parse_model_name(value: str) -> str:
    """Accept only short lowercase names so outputs cannot escape their folders."""
    if not MODEL_NAME_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "Model name must be 1-40 characters of lowercase letters, digits, or underscores."
        )
    return value


def _parse_modes(value: str) -> ModeGrid:
    """Parse supported embedding mode names."""
    modes = tuple(value.split(","))
    if not modes or any(mode not in DEFAULT_MODES for mode in modes):
        raise argparse.ArgumentTypeError("Modes must be keyed and/or sequential.")
    return modes  # type: ignore[return-value]


if __name__ == "__main__":
    raise SystemExit(main())
