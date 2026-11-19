"""Tests for the CNN training command-line options (no training is run)."""

import pytest

from scripts.train_cnn import build_parser, output_file_names


def test_default_run_keeps_original_output_names() -> None:
    """Existing notebooks and docs reference these exact cnn_v1 filenames."""
    assert output_file_names("cnn_v1") == {
        "checkpoint": "cnn_v1.pt",
        "intermediate": "cnn_v1_best.tmp.pt",
        "metadata": "cnn_v1.json",
        "metrics": "cnn_metrics.json",
        "curves": "cnn_training_curves.png",
    }


def test_named_run_cannot_overwrite_cnn_v1() -> None:
    """A second experiment writes only files prefixed with its own name."""
    names = output_file_names("cnn_mismatch_replace")
    assert all(value.startswith("cnn_mismatch_replace") for value in names.values())


def test_parser_defaults_train_on_both_methods() -> None:
    """Without flags, training follows the blueprint's replace/match mixture."""
    args = build_parser().parse_args(["--dataset", "data"])
    assert args.train_methods == ("lsb_replace", "lsb_match")
    assert args.model_name == "cnn_v1"


def test_parser_accepts_mismatch_experiment() -> None:
    """Train on replacement only while still testing on both methods."""
    args = build_parser().parse_args(
        [
            "--dataset",
            "data",
            "--train-methods",
            "lsb_replace",
            "--model-name",
            "cnn_mismatch_replace",
        ]
    )
    assert args.train_methods == ("lsb_replace",)
    assert args.methods == ("lsb_replace", "lsb_match")


@pytest.mark.parametrize("bad_name", ["../escape", "CNN", "", "a" * 41, "cnn v1"])
def test_parser_rejects_unsafe_model_names(bad_name: str) -> None:
    """Names become file paths, so separators and odd characters are refused."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dataset", "data", "--model-name", bad_name])
