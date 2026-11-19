"""Tests for the model-card generator: numbers come only from the metrics file."""

import json
from pathlib import Path

import pytest

from scripts.make_model_card import END, START, main, render, replace_block, weakest_conditions

ENTRY = {
    "roc_auc": 0.9,
    "p_e": 0.12,
    "tpr_at_1pct_fpr": 0.5,
    "accuracy": 0.88,
    "roc_auc_ci95": [0.88, 0.92],
}


def _metrics(with_cnn: bool) -> dict:
    detectors = {"classical": {"label": "Classical ML", "trained": True, "source": "x"}}
    entries = {"classical": ENTRY}
    if with_cnn:
        detectors["cnn_v1"] = {"label": "CNN", "trained": True, "source": "x"}
        entries["cnn_v1"] = {**ENTRY, "roc_auc": 0.7}
    conditions = [
        {"method": "lsb_replace", "mode": "keyed", "payload_bpp": 0.05, "detectors": entries},
        {"method": "lsb_match", "mode": "keyed", "payload_bpp": 0.4, "detectors": entries},
    ]
    return {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "detectors": detectors,
        "conditions": conditions,
        "mismatch": None,
        "notes": ["note one"],
    }


def test_render_without_cnn_says_not_trained() -> None:
    """With no CNN in the metrics the card must say so, not invent a status."""
    text = render(_metrics(with_cnn=False), None)
    assert "CNN not trained" in text
    assert "0.900 [0.88, 0.92]" in text
    assert "note one" in text


def test_render_with_cnn_uses_sidecar_values() -> None:
    """Training facts come from cnn_v1.json."""
    meta = {
        "hyperparameters": {
            "epochs_completed": 12,
            "best_epoch": 9,
            "device": "cuda",
            "training_methods": ["lsb_replace"],
        },
        "training_time_seconds": 7200,
        "seed": 1337,
        "temperature": 1.234,
        "dataset_origin": "TestSet",
        "split_counts": {"train": 7},
    }
    text = render(_metrics(with_cnn=True), meta)
    assert "completed 12 epochs" in text and "best epoch 9" in text
    assert "2.00 h" in text and "1.234" in text and "TestSet" in text


def test_weakest_conditions_are_sorted_by_auc() -> None:
    """The hardest condition is listed first, computed from the data."""
    metrics = _metrics(with_cnn=True)
    metrics["conditions"][1]["detectors"]["cnn_v1"]["roc_auc"] = 0.55
    assert "0.550" in weakest_conditions(metrics, "cnn_v1", 1)[0]


def test_replace_block_keeps_surrounding_text() -> None:
    """Only the marked block changes."""
    card = f"before\n{START}\nold\n{END}\nafter\n"
    updated = replace_block(card, "new block\n")
    assert updated.startswith("before\n") and updated.endswith("\nafter\n")
    assert "old" not in updated and "new block" in updated
    with pytest.raises(ValueError):
        replace_block("no markers", "x")


def test_main_rewrites_card_and_fails_without_metrics(tmp_path: Path) -> None:
    """End to end on temp files; a missing metrics file is an error."""
    card = tmp_path / "card.md"
    card.write_text(f"intro\n{START}\nplaceholder\n{END}\noutro\n", encoding="utf-8")
    metrics = tmp_path / "metrics.json"
    assert (
        main(["--metrics", str(metrics), "--card", str(card), "--cnn-meta", str(tmp_path / "none")])
        == 1
    )
    metrics.write_text(json.dumps(_metrics(with_cnn=False)), encoding="utf-8")
    assert (
        main(["--metrics", str(metrics), "--card", str(card), "--cnn-meta", str(tmp_path / "none")])
        == 0
    )
    text = card.read_text(encoding="utf-8")
    assert "placeholder" not in text and text.startswith("intro") and text.endswith("outro\n")


def test_unseen_techniques_get_their_own_labelled_section() -> None:
    """Results for untrained techniques are listed after the trained ones, with an explanation."""
    metrics = _metrics(with_cnn=False)
    metrics["conditions"].append(
        {
            "method": "suniward_sim",
            "mode": "simulated",
            "payload_bpp": 0.4,
            "detectors": {"classical": ENTRY},
        }
    )
    text = render(metrics, None)
    assert "### Unseen techniques" in text and "S-UNIWARD simulation (unseen in training)" in text
    assert text.index("LSB replacement, keyed") < text.index(
        "S-UNIWARD simulation (unseen in training), simulated"
    )
    assert "### Unseen techniques" not in render(_metrics(with_cnn=False), None)
