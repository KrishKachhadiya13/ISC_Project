"""Tests for Phase 5 statistical detectors, features, and model training."""

import json
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from app.core.stego.embed import embed
from app.steganalysis.classical.chi_square import (
    chi_square_attack,
    progressive_chi_square,
)
from app.steganalysis.classical.features import (
    FEATURE_NAMES,
    extract_features,
    statistical_fallback,
)
from app.steganalysis.classical.rf_model import (
    classification_metrics,
    save_models,
    select_f1_threshold,
    train_classifiers,
)
from app.steganalysis.classical.rs import rs_analysis
from app.steganalysis.classical.spa import sample_pair_analysis
from scripts.train_classical import main

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "cc0_spruce_forest.jpg"


def _natural_photo() -> NDArray[np.uint8]:
    """Load the small CC0 photo as a 256×256 grayscale cover."""
    with Image.open(FIXTURE_PATH) as image:
        image.load()
        return np.asarray(
            image.convert("L").resize((256, 256), Image.Resampling.LANCZOS),
            dtype=np.uint8,
        )


def _embedded_photo(mode: str) -> NDArray[np.uint8]:
    """Create a deterministic 0.4 bpp LSB-replacement photo for attack tests."""
    cover = _natural_photo()
    payload_length = (int(0.4 * cover.size) - 104 - (128 if mode == "keyed" else 0)) // 8
    payload = np.random.default_rng(42).bytes(payload_length)
    return embed(
        cover,
        payload,
        mode=mode,  # type: ignore[arg-type]
        stego_passphrase="test-only-not-a-project-key" if mode == "keyed" else None,
        stego_salt=b"0123456789abcdef" if mode == "keyed" else None,
    )


def test_chi_square_balanced_pairs_and_progressive_final_row() -> None:
    """Balanced value pairs have zero statistic and the prefix reaches image end."""
    balanced = np.tile(np.array([2, 3], dtype=np.uint8), (32, 32))
    result = chi_square_attack(balanced)
    progressive = progressive_chi_square(balanced, row_step=7)

    assert result.statistic == 0.0
    assert result.p_value == pytest.approx(1.0)
    assert result.degrees_of_freedom == 1
    assert [item.end_row for item in progressive] == [7, 14, 21, 28, 32]


def test_detector_inputs_and_small_images_are_validated() -> None:
    """Invalid domains fail explicitly while tiny images yield finite estimates."""
    with pytest.raises(ValueError, match="uint8"):
        chi_square_attack(np.zeros((2, 2), dtype=np.int16))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        progressive_chi_square(np.zeros((2, 2), dtype=np.uint8), row_step=0)

    tiny = np.zeros((1, 1), dtype=np.uint8)
    rs_result = rs_analysis(tiny)
    spa_result = sample_pair_analysis(tiny)
    assert rs_result.group_count == 0
    assert rs_result.estimated_rate == 0.0
    assert spa_result.pair_count == 0
    assert spa_result.estimated_rate == 0.0


def test_feature_extractor_rejects_invalid_image_shapes() -> None:
    """Only non-empty grayscale and three-channel uint8 arrays are supported."""
    with pytest.raises(ValueError, match="uint8"):
        extract_features(np.zeros((8, 8), dtype=np.int16))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="grayscale or RGB"):
        extract_features(np.zeros((8, 8, 4), dtype=np.uint8))  # type: ignore[arg-type]


@pytest.mark.slow
@pytest.mark.parametrize("mode", ["sequential", "keyed"])
def test_natural_photo_detectors_respond_to_lsb_replacement(mode: str) -> None:
    """A CC0 natural photo shows loose attack-score changes after 0.4 bpp embedding."""
    cover = _natural_photo()
    stego = _embedded_photo(mode)
    cover_chi = chi_square_attack(cover)
    stego_chi = chi_square_attack(stego)
    cover_rs = rs_analysis(cover)
    stego_rs = rs_analysis(stego)
    cover_spa = sample_pair_analysis(cover)
    stego_spa = sample_pair_analysis(stego)

    assert cover_rs.estimated_rate < 0.25
    assert cover_spa.estimated_rate < 0.15
    assert stego_chi.p_value > cover_chi.p_value
    assert stego_rs.estimated_rate > cover_rs.estimated_rate
    assert stego_spa.estimated_rate > cover_spa.estimated_rate


def test_sequential_progressive_chi_square_changes_after_embedded_prefix() -> None:
    """Sequential embedding changes histogram-pair evidence in the touched prefix."""
    stego = _embedded_photo("sequential")
    prefix_results = progressive_chi_square(stego, row_step=32)
    before_payload_end = prefix_results[2].result.p_value
    after_payload_end = prefix_results[3].result.p_value
    assert abs(np.log10(before_payload_end) - np.log10(after_payload_end)) > 0.1


def test_feature_schema_is_stable_finite_and_channel_aggregated() -> None:
    """Grayscale and RGB inputs return the same named finite feature schema."""
    grayscale = _natural_photo()
    gray_features = extract_features(grayscale)
    rgb_features = extract_features(np.repeat(grayscale[:, :, None], 3, axis=2))

    assert len(FEATURE_NAMES) == 1068
    assert gray_features.shape == (len(FEATURE_NAMES),)
    assert rgb_features.shape == gray_features.shape
    assert np.isfinite(gray_features).all()
    assert np.isfinite(rgb_features).all()
    assert np.array_equal(gray_features, rgb_features)


def test_statistical_fallback_is_labelled_and_json_safe() -> None:
    """Untrained detector identifies its status and returns finite component scores."""
    output = statistical_fallback(_natural_photo())

    assert output["model"] == "statistical (untrained)"
    assert output["label"] in {"clean", "suspected_stego"}
    assert 0.0 <= output["probability"] <= 1.0
    assert set(output["detectors"]) == {"chi_square", "rs", "spa"}
    json.dumps(output, allow_nan=False)


def test_models_train_evaluate_and_write_metadata(tmp_path: Path) -> None:
    """Both requested classifiers train and sidecars retain schema and provenance."""
    rng = np.random.default_rng(7)
    features = rng.normal(size=(12, len(FEATURE_NAMES))).astype(np.float32)
    labels = np.array([0, 1] * 6, dtype=np.int8)
    models = train_classifiers(features, labels, seed=3, forest_trees=5, hgb_iterations=3)
    probabilities = models.random_forest.predict_proba(features)[:, 1]
    metrics = classification_metrics(labels, (probabilities >= 0.5).astype(np.int8), probabilities)
    output = tmp_path / "models"
    save_models(
        models,
        output,
        training_data_sha256="a" * 64,
        seed=3,
        dataset_origin="unit test data",
        experiment={"smoke_test": True},
    )
    metadata = json.loads((output / "classical_rf.json").read_text(encoding="utf-8"))

    assert set(metrics) >= {"accuracy", "precision", "recall", "f1", "roc_auc"}
    assert (output / "classical_rf.joblib").is_file()
    assert (output / "classical_hgb.joblib").is_file()
    assert metadata["feature_names"] == list(FEATURE_NAMES)
    assert metadata["training_data_sha256"] == "a" * 64
    assert metadata["seed"] == 3
    assert "scikit_learn" in metadata["versions"]


def test_validation_threshold_selection_uses_validation_labels() -> None:
    """F1 threshold tuning returns a finite operating point for both classes."""
    labels = np.array([0, 0, 1, 1], dtype=np.int8)
    probabilities = np.array([0.1, 0.4, 0.6, 0.9], dtype=np.float64)

    threshold = select_f1_threshold(labels, probabilities)

    assert 0.0 <= threshold <= 1.0
    assert np.mean((probabilities >= threshold) == labels) == 1.0


def test_model_helpers_reject_invalid_training_and_metric_inputs() -> None:
    """Model and metric validation fail clearly instead of fitting bad data."""
    good_features = np.zeros((2, len(FEATURE_NAMES)), dtype=np.float32)
    good_labels = np.array([0, 1], dtype=np.int8)

    with pytest.raises(ValueError, match="shape"):
        train_classifiers(np.zeros((2, 1), dtype=np.float32), good_labels, seed=1)
    with pytest.raises(ValueError, match="match the feature"):
        train_classifiers(good_features, np.array([0], dtype=np.int8), seed=1)
    with pytest.raises(ValueError, match="both cover"):
        train_classifiers(good_features, np.array([0, 0], dtype=np.int8), seed=1)
    with pytest.raises(ValueError, match="positive"):
        train_classifiers(good_features, good_labels, seed=1, forest_trees=0)
    non_finite = good_features.copy()
    non_finite[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        train_classifiers(non_finite, good_labels, seed=1)
    with pytest.raises(ValueError, match="matching 1-D"):
        classification_metrics(
            good_labels,
            np.array([0], dtype=np.int8),
            np.array([0.1, 0.9], dtype=np.float64),
        )
    with pytest.raises(ValueError, match="both classes"):
        classification_metrics(
            np.array([0, 0], dtype=np.int8),
            np.array([0, 0], dtype=np.int8),
            np.array([0.1, 0.2], dtype=np.float64),
        )
    with pytest.raises(ValueError, match="finite"):
        select_f1_threshold(good_labels, np.array([np.nan, 0.9], dtype=np.float64))


def test_training_cli_smoke_writes_split_metrics(tmp_path: Path) -> None:
    """A tiny generated dataset exercises the full train/evaluate CLI contract."""
    dataset = tmp_path / "prepared"
    dataset.mkdir()
    splits = {
        "train": ["cover_00000", "cover_00001"],
        "val": ["cover_00002", "cover_00003"],
        "test": ["cover_00004", "cover_00005"],
    }
    rng = np.random.default_rng(12)
    for cover_id in (item for ids in splits.values() for item in ids):
        samples = rng.integers(16, 240, size=(32, 32), dtype=np.uint8)
        Image.fromarray(samples, mode="L").save(dataset / f"{cover_id}.png")
    (dataset / "splits.json").write_text(
        json.dumps({"seed": 12, "splits": splits}),
        encoding="utf-8",
    )
    (dataset / "dataset_card.json").write_text(
        json.dumps({"origin": "synthetic smoke test only"}),
        encoding="utf-8",
    )
    models_out = tmp_path / "models"
    results_out = tmp_path / "results.json"

    exit_code = main(
        [
            "--dataset",
            str(dataset),
            "--models-out",
            str(models_out),
            "--results-out",
            str(results_out),
            "--payloads",
            "0.3",
            "--methods",
            "lsb_replace",
            "--modes",
            "sequential",
            "--forest-trees",
            "5",
            "--hgb-iterations",
            "3",
        ]
    )
    results = json.loads(results_out.read_text(encoding="utf-8"))
    evaluation = results["evaluations"]["lsb_replace|sequential|0.3"]

    assert exit_code == 0
    assert results["dataset_origin"] == "synthetic smoke test only"
    assert results["splits"]["test"]["cover_count"] == 2
    assert set(evaluation["val"]) == {
        "random_forest",
        "histogram_gradient_boosting",
        "statistical_fallback",
    }
    assert set(evaluation["test"]) == set(evaluation["val"])
    assert (models_out / "classical_rf.joblib").is_file()
