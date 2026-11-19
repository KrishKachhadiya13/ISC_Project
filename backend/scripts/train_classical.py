"""Train and evaluate the Phase 5 classical steganalysis pipeline."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.stego.embed import EmbeddingMethod, EmbeddingMode, embed, maximum_payload_bytes
from app.steganalysis.classical.features import (
    FEATURE_NAMES,
    extract_features,
    statistical_fallback,
)
from app.steganalysis.classical.rf_model import (
    ClassicalModels,
    classification_metrics,
    save_models,
    select_f1_threshold,
    train_classifiers,
)

FeatureMatrix: TypeAlias = NDArray[np.float32]
LabelVector: TypeAlias = NDArray[np.int8]
DEFAULT_SEED = 1337
DEFAULT_METHODS: tuple[EmbeddingMethod, ...] = ("lsb_replace", "lsb_match")
DEFAULT_MODES: tuple[EmbeddingMode, ...] = ("sequential", "keyed")
DEFAULT_PAYLOADS = (0.05, 0.1, 0.2, 0.4, 1.0)


def build_parser() -> argparse.ArgumentParser:
    """Create the training CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path, help="Prepared covers directory.")
    parser.add_argument("--models-out", required=True, type=Path, help="Model output directory.")
    parser.add_argument("--results-out", required=True, type=Path, help="Metrics JSON output.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--payloads",
        type=_parse_payloads,
        default=DEFAULT_PAYLOADS,
        help="Comma-separated target payload rates in bits per pixel (default: 0.05,0.1,0.2,0.4).",
    )
    parser.add_argument(
        "--methods",
        type=_parse_methods,
        default=DEFAULT_METHODS,
        help="Comma-separated embed methods: lsb_replace,lsb_match.",
    )
    parser.add_argument(
        "--modes",
        type=_parse_modes,
        default=DEFAULT_MODES,
        help="Comma-separated embed modes: sequential,keyed.",
    )
    parser.add_argument(
        "--max-covers-per-split",
        type=int,
        help="Optional cap for smoke tests; do not use for final evaluation.",
    )
    parser.add_argument("--forest-trees", type=int, default=300)
    parser.add_argument("--hgb-iterations", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Prepare labelled stego variants, train both models, and save held-out metrics."""
    args = build_parser().parse_args(argv)
    try:
        if args.seed < 0:
            raise ValueError("Seed must be non-negative.")
        if args.max_covers_per_split is not None and args.max_covers_per_split < 2:
            raise ValueError("At least two covers per split are required.")
        if "keyed" in args.modes and not os.environ.get("STEGAGUARD_TRAINING_PASSPHRASE"):
            raise ValueError(
                "Keyed-mode training requires STEGAGUARD_TRAINING_PASSPHRASE in the environment."
            )
        splits, dataset_origin = _load_split_data(args.dataset, args.max_covers_per_split)
        dataset_hash = _hash_training_data(args.dataset, splits)
        experiment = {
            "seed": args.seed,
            "payloads_bits_per_pixel": list(args.payloads),
            "methods": list(args.methods),
            "modes": list(args.modes),
            "split_counts": {name: len(ids) for name, ids in splits.items()},
            "max_covers_per_split": args.max_covers_per_split,
            "note": (
                "A capped smoke run is not a benchmark; use full splits for evaluation."
                if args.max_covers_per_split is not None
                else "Metrics are from the held-out cover-level test split."
            ),
        }
        data = _build_examples(
            args.dataset,
            splits,
            args.payloads,
            args.methods,
            args.modes,
            args.seed,
            os.environ.get("STEGAGUARD_TRAINING_PASSPHRASE"),
        )
        models = train_classifiers(
            data["train"][0],
            data["train"][1],
            args.seed,
            args.forest_trees,
            args.hgb_iterations,
        )
        thresholds = _select_validation_thresholds(
            models,
            data["val"],
            args.payloads,
            args.methods,
            args.modes,
        )
        experiment["decision_thresholds_selected_on_validation"] = thresholds
        results = _evaluate_all(
            models,
            data,
            args.dataset,
            splits,
            thresholds,
            args.payloads,
            args.methods,
            args.modes,
            dataset_hash,
            dataset_origin,
            args.seed,
            experiment,
        )
        args.models_out.mkdir(parents=True, exist_ok=True)
        args.results_out.parent.mkdir(parents=True, exist_ok=True)
        save_models(
            models,
            args.models_out,
            training_data_sha256=dataset_hash,
            seed=args.seed,
            dataset_origin=dataset_origin,
            experiment=experiment,
        )
        args.results_out.write_text(
            json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"Classical model training failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved trained models to {args.models_out}")
    print(f"Saved held-out evaluation metrics to {args.results_out}")
    if args.max_covers_per_split is not None:
        print("WARNING: capped smoke run; these metrics are not benchmark results.")
    return 0


def _build_examples(
    dataset_dir: Path,
    splits: dict[str, list[str]],
    payloads: tuple[float, ...],
    methods: tuple[EmbeddingMethod, ...],
    modes: tuple[EmbeddingMode, ...],
    seed: int,
    passphrase: str | None,
) -> dict[str, tuple[FeatureMatrix, LabelVector, dict[str, FeatureMatrix]]]:
    """Build cover/stego features separately for each cover-level split."""
    examples: dict[str, tuple[FeatureMatrix, LabelVector, dict[str, FeatureMatrix]]] = {}
    seen_salts: set[bytes] = set()
    for split_name, cover_ids in splits.items():
        clean_features: list[NDArray[np.float32]] = []
        variant_features: dict[str, list[NDArray[np.float32]]] = {}
        for cover_id in cover_ids:
            cover = _load_cover(dataset_dir / f"{cover_id}.png")
            clean_features.append(extract_features(cover))
            for method in methods:
                for mode in modes:
                    for payload_bpp in payloads:
                        key = _condition_key(method, mode, payload_bpp)
                        stego, salt = _make_stego(
                            cover,
                            cover_id,
                            payload_bpp,
                            method,
                            mode,
                            seed,
                            passphrase,
                        )
                        if salt is not None:
                            if salt in seen_salts:
                                raise RuntimeError(
                                    "Generated duplicate salt in keyed training variants."
                                )
                            seen_salts.add(salt)
                        variant_features.setdefault(key, []).append(extract_features(stego))

        clean_matrix = np.stack(clean_features).astype(np.float32)
        variant_matrices = {
            key: np.stack(features).astype(np.float32) for key, features in variant_features.items()
        }
        if split_name == "train":
            matrices = [clean_matrix, *variant_matrices.values()]
            labels = [
                np.zeros(clean_matrix.shape[0], dtype=np.int8),
                *[np.ones(matrix.shape[0], dtype=np.int8) for matrix in variant_matrices.values()],
            ]
            features = np.concatenate(matrices)
            targets = np.concatenate(labels)
        else:
            features = clean_matrix
            targets = np.zeros(clean_matrix.shape[0], dtype=np.int8)
        examples[split_name] = (features, targets, variant_matrices)
    return examples


def _make_stego(
    cover: NDArray[np.uint8],
    cover_id: str,
    payload_bpp: float,
    method: EmbeddingMethod,
    mode: EmbeddingMode,
    seed: int,
    passphrase: str | None,
) -> tuple[NDArray[np.uint8], bytes | None]:
    """Generate a deterministic, uniquely salted stego sample for training."""
    sample_count = int(cover.size)
    budget = int(payload_bpp * sample_count)
    reserved_bits = 128 if mode == "keyed" else 0
    payload_bytes = max(
        0, min((budget - 104 - reserved_bits) // 8, maximum_payload_bytes(sample_count, mode))
    )
    if payload_bytes < 1:
        raise ValueError(
            f"Payload {payload_bpp} bpp is too small for the image size {cover.shape}."
        )
    token = f"{seed}|{cover_id}|{method}|{mode}|{payload_bpp:.8g}".encode()
    rng = np.random.default_rng(
        np.random.SeedSequence([seed, int.from_bytes(hashlib.sha256(token).digest()[:4], "big")])
    )
    payload = rng.bytes(payload_bytes)
    salt = (
        hashlib.sha256(b"stegaguard-training-salt|" + token).digest()[:16]
        if mode == "keyed"
        else None
    )
    coin_flips = rng.bytes(sample_count) if method == "lsb_match" else None
    stego = embed(
        cover,
        payload,
        method=method,
        mode=mode,
        stego_passphrase=passphrase if mode == "keyed" else None,
        stego_salt=salt,
        matching_randomness=coin_flips,
    )
    return stego, salt


def _evaluate_all(
    models: ClassicalModels,
    data: dict[str, tuple[FeatureMatrix, LabelVector, dict[str, FeatureMatrix]]],
    dataset_dir: Path,
    splits: dict[str, list[str]],
    thresholds: dict[str, float],
    payloads: tuple[float, ...],
    methods: tuple[EmbeddingMethod, ...],
    modes: tuple[EmbeddingMode, ...],
    dataset_hash: str,
    dataset_origin: str,
    seed: int,
    experiment: dict[str, object],
) -> dict[str, object]:
    """Evaluate every condition on validation and held-out test covers."""
    evaluations: dict[str, object] = {}
    for method in methods:
        for mode in modes:
            for payload_bpp in payloads:
                key = _condition_key(method, mode, payload_bpp)
                configuration: dict[str, object] = {
                    "method": method,
                    "mode": mode,
                    "payload_bits_per_pixel": payload_bpp,
                }
                for split_name in ("val", "test"):
                    clean_matrix, _, variant_matrices = data[split_name]
                    stego_matrix = variant_matrices[key]
                    matrix = np.concatenate((clean_matrix, stego_matrix))
                    labels = np.concatenate(
                        (
                            np.zeros(clean_matrix.shape[0], dtype=np.int8),
                            np.ones(stego_matrix.shape[0], dtype=np.int8),
                        )
                    )
                    model_metrics: dict[str, object] = {}
                    for model_name, model in (
                        ("random_forest", models.random_forest),
                        ("histogram_gradient_boosting", models.histogram_gradient_boosting),
                    ):
                        probabilities = model.predict_proba(matrix)[:, 1]
                        predictions = (probabilities >= thresholds[model_name]).astype(np.int8)
                        model_metrics[model_name] = classification_metrics(
                            labels, predictions, probabilities
                        )
                    cover_ids = splits[split_name]
                    clean_fallback = np.asarray(
                        [
                            float(
                                statistical_fallback(_load_cover(dataset_dir / f"{cover_id}.png"))[
                                    "probability"
                                ]
                            )
                            for cover_id in cover_ids
                        ],
                        dtype=np.float64,
                    )
                    fallback_values = np.concatenate(
                        (
                            clean_fallback,
                            _fallback_probabilities(
                                dataset_dir,
                                cover_ids,
                                method,
                                mode,
                                payload_bpp,
                                seed,
                            ),
                        )
                    )
                    model_metrics["statistical_fallback"] = classification_metrics(
                        labels,
                        (fallback_values >= 0.5).astype(np.int8),
                        fallback_values,
                    )
                    configuration[split_name] = model_metrics
                evaluations[key] = configuration
    return {
        "format_version": 1,
        "training_data_sha256": dataset_hash,
        "dataset_origin": dataset_origin,
        "feature_count": len(FEATURE_NAMES),
        "seed": seed,
        "experiment": experiment,
        "splits": {
            name: {"cover_count": len(ids), "cover_ids": ids} for name, ids in splits.items()
        },
        "evaluations": evaluations,
    }


def _select_validation_thresholds(
    models: ClassicalModels,
    validation_data: tuple[FeatureMatrix, LabelVector, dict[str, FeatureMatrix]],
    payloads: tuple[float, ...],
    methods: tuple[EmbeddingMethod, ...],
    modes: tuple[EmbeddingMode, ...],
) -> dict[str, float]:
    """Tune model decision thresholds on all validation configurations."""
    clean_matrix = validation_data[0]
    feature_rows: list[FeatureMatrix] = []
    labels: list[LabelVector] = []
    for method in methods:
        for mode in modes:
            for payload_bpp in payloads:
                stego_matrix = validation_data[2][_condition_key(method, mode, payload_bpp)]
                feature_rows.append(np.concatenate((clean_matrix, stego_matrix)))
                labels.append(
                    np.concatenate(
                        (
                            np.zeros(clean_matrix.shape[0], dtype=np.int8),
                            np.ones(stego_matrix.shape[0], dtype=np.int8),
                        )
                    )
                )
    validation_features = np.concatenate(feature_rows)
    validation_labels = np.concatenate(labels)
    return {
        model_name: select_f1_threshold(
            validation_labels,
            model.predict_proba(validation_features)[:, 1],
        )
        for model_name, model in (
            ("random_forest", models.random_forest),
            ("histogram_gradient_boosting", models.histogram_gradient_boosting),
        )
    }


def _fallback_probabilities(
    dataset_dir: Path,
    cover_ids: list[str],
    method: EmbeddingMethod,
    mode: EmbeddingMode,
    payload_bpp: float,
    seed: int,
) -> NDArray[np.float64]:
    """Compute transparent fallback scores on the exact held-out stego variants."""
    passphrase = os.environ.get("STEGAGUARD_TRAINING_PASSPHRASE") if mode == "keyed" else None
    scores = []
    for cover_id in cover_ids:
        cover = _load_cover(dataset_dir / f"{cover_id}.png")
        stego, _ = _make_stego(cover, cover_id, payload_bpp, method, mode, seed, passphrase)
        scores.append(float(statistical_fallback(stego)["probability"]))
    return np.asarray(scores, dtype=np.float64)


def _load_split_data(
    dataset_dir: Path,
    max_covers_per_split: int | None,
) -> tuple[dict[str, list[str]], str]:
    """Validate metadata and load disjoint, cover-level split IDs."""
    split_data = _split_data(dataset_dir)
    if max_covers_per_split is not None:
        split_data = {name: ids[:max_covers_per_split] for name, ids in split_data.items()}
    if any(len(ids) < 2 for ids in split_data.values()):
        raise ValueError("Train, val, and test splits each require at least two covers.")
    all_ids = [cover_id for ids in split_data.values() for cover_id in ids]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Cover IDs must not occur in more than one split.")
    for cover_id in all_ids:
        if not (dataset_dir / f"{cover_id}.png").is_file():
            raise FileNotFoundError(f"Missing cover image {dataset_dir / f'{cover_id}.png'}.")
    card_path = dataset_dir / "dataset_card.json"
    if not card_path.is_file():
        raise FileNotFoundError(f"Missing dataset card: {card_path}")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    origin = card.get("origin")
    if not isinstance(origin, str) or not origin.strip():
        raise ValueError("Dataset card must include a non-empty source origin.")
    return split_data, origin


def _split_data(dataset_dir: Path) -> dict[str, list[str]]:
    """Read the Phase 4 ``splits.json`` structure."""
    path = dataset_dir / "splits.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing split metadata: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    split_map = data.get("splits")
    if not isinstance(split_map, dict) or set(split_map) != {"train", "val", "test"}:
        raise ValueError("splits.json must contain train, val, and test lists.")
    if any(not isinstance(split_map[name], list) for name in ("train", "val", "test")):
        raise ValueError("Each split must be a list of cover IDs.")
    splits = {name: split_map[name] for name in ("train", "val", "test")}
    if any(
        not isinstance(cover_id, str) or re.fullmatch(r"cover_\d{5}", cover_id) is None
        for ids in splits.values()
        for cover_id in ids
    ):
        raise ValueError("Cover IDs must use the prepared dataset format 'cover_00000'.")
    return splits


def _load_cover(path: Path) -> NDArray[np.uint8]:
    """Decode a prepared grayscale PNG cover without silently coercing modes."""
    try:
        with Image.open(path) as image:
            image.load()
            if image.mode != "L":
                raise ValueError(f"Prepared cover must be grayscale: {path}")
            return np.asarray(image, dtype=np.uint8).copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Could not decode prepared cover {path}: {exc}") from exc


def _hash_training_data(dataset_dir: Path, splits: dict[str, list[str]]) -> str:
    """Hash exact bytes for the cover-level training set in stable ID order."""
    digest = hashlib.sha256()
    training_ids = sorted(splits["train"])
    digest.update(json.dumps(training_ids, separators=(",", ":")).encode("utf-8"))
    for cover_id in training_ids:
        path = dataset_dir / f"{cover_id}.png"
        digest.update(cover_id.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _condition_key(method: str, mode: str, payload_bpp: float) -> str:
    """Build stable result keys for embedding configurations."""
    return f"{method}|{mode}|{payload_bpp:.8g}"


def _parse_payloads(value: str) -> tuple[float, ...]:
    """Parse and validate a comma-separated payload-rate list."""
    try:
        payloads = tuple(float(part) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Payloads must be comma-separated numbers.") from exc
    if not payloads or any(not 0 < payload <= 1 for payload in payloads):
        raise argparse.ArgumentTypeError("Payloads must be greater than 0 and at most 1 bpp.")
    return payloads


def _parse_methods(value: str) -> tuple[EmbeddingMethod, ...]:
    """Parse and validate embedding method names."""
    methods = tuple(value.split(","))
    if not methods or any(item not in DEFAULT_METHODS for item in methods):
        raise argparse.ArgumentTypeError("Methods must be lsb_replace and/or lsb_match.")
    return methods  # type: ignore[return-value]


def _parse_modes(value: str) -> tuple[EmbeddingMode, ...]:
    """Parse and validate embedding mode names."""
    modes = tuple(value.split(","))
    if not modes or any(item not in DEFAULT_MODES for item in modes):
        raise argparse.ArgumentTypeError("Modes must be sequential and/or keyed.")
    return modes  # type: ignore[return-value]


if __name__ == "__main__":
    raise SystemExit(main())
