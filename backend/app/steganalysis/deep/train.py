"""StegNet-Lite training, validation selection, calibration, and evaluation."""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from torch import Tensor, nn
from torch.utils.data import DataLoader

from app.steganalysis.deep.calibration import calibrated_probabilities, fit_temperature
from app.steganalysis.deep.dataset import (
    TRAINING_PAYLOAD_BPP,
    StegoPairDataset,
)
from app.steganalysis.deep.model import StegNetLite

logger = logging.getLogger(__name__)

# Epochs 1-8 train only on payloads >= 0.4 bpp (Section 6.9 curriculum).
CURRICULUM_EPOCHS = 8


@dataclass(frozen=True)
class TrainingConfig:
    """Reproducible optimization and curriculum settings."""

    seed: int = 1337
    epochs: int = 40
    batch_pairs: int = 32
    learning_rate: float = 3e-4
    warmup_steps: int = 200
    weight_decay: float = 1e-4
    patience: int = 8
    gradient_clip: float = 1.0
    truncation: float = 3.0
    num_workers: int = 0


@dataclass(frozen=True)
class TrainingResult:
    """Best checkpoint, per-epoch history, and validation operating point."""

    model: StegNetLite
    history: list[dict[str, float]]
    best_epoch: int
    best_validation_auc: float
    best_validation_pe: float
    validation_threshold: float
    temperature: float
    elapsed_seconds: float


def train_model(
    model: StegNetLite,
    train_dataset: StegoPairDataset,
    validation_loader: DataLoader[tuple[Tensor, Tensor]],
    checkpoint_path: Path,
    config: TrainingConfig,
    device: torch.device,
    validation_groups: Sequence[tuple[str, int]] = (),
) -> TrainingResult:
    """Train with AdamW, cosine decay, curriculum sampling, and early stopping."""
    if config.epochs < 1 or config.batch_pairs < 1 or config.patience < 1:
        raise ValueError("Epochs, batch size, and patience must be positive.")
    if config.learning_rate <= 0 or config.weight_decay < 0:
        raise ValueError("Learning rate must be positive and weight decay non-negative.")
    if config.gradient_clip <= 0 or config.num_workers < 0:
        raise ValueError("Gradient clip must be positive and worker count non-negative.")
    if not len(train_dataset) or not len(validation_loader.dataset):  # type: ignore[arg-type]
        raise ValueError("Training and validation datasets must not be empty.")

    torch.manual_seed(config.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(config.seed)
    model = model.to(device)
    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_pairs,
        shuffle=True,
        num_workers=config.num_workers,
        pin_memory=device.type == "cuda",
        drop_last=False,
    )
    optimizer = torch.optim.AdamW(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs)
    scaler = torch.cuda.amp.GradScaler(enabled=device.type == "cuda")
    loss_function = nn.BCEWithLogitsLoss()
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    history: list[dict[str, float]] = []
    best_auc = -1.0
    best_pe = 1.0
    best_epoch = 0
    best_threshold = 0.5
    epochs_without_improvement = 0
    start_time = time.perf_counter()

    for epoch in range(config.epochs):
        train_dataset.set_epoch(epoch, _curriculum_payloads(epoch))
        model.train()
        train_loss = _train_epoch(
            model,
            train_loader,
            optimizer,
            loss_function,
            scaler,
            device,
            config.gradient_clip,
            warmup_steps=config.warmup_steps if epoch == 0 else 0,
            base_learning_rate=config.learning_rate,
        )
        scheduler.step()
        validation_logits, validation_labels, validation_loss = evaluate_logits(
            model,
            validation_loader,
            device,
            loss_function,
        )
        validation_auc = float(roc_auc_score(validation_labels, validation_logits))
        validation_pe, threshold = minimum_detection_error(validation_labels, validation_logits)
        history.append(
            {
                "epoch": float(epoch + 1),
                "train_loss": train_loss,
                "validation_loss": validation_loss,
                "validation_auc": validation_auc,
                "validation_pe": validation_pe,
                "learning_rate": float(optimizer.param_groups[0]["lr"]),
            }
        )

        group_aucs = _group_aucs(validation_logits, validation_labels, validation_groups)
        for name, group_auc in group_aucs.items():
            history[-1][f"val_auc_{name}"] = group_auc
        if group_aucs:
            logger.info(
                "  per-condition val AUC: %s",
                ", ".join(f"{name}={value:.3f}" for name, value in group_aucs.items()),
            )
        # Always keep the newest weights too, so a collapse can be inspected afterwards.
        _save_state_dict(model, checkpoint_path.with_name(f"{checkpoint_path.stem}_last.pt"))
        logger.info(
            "epoch %d/%d train_loss=%.4f val_loss=%.4f val_auc=%.4f val_pe=%.4f (%.0fs elapsed)",
            epoch + 1,
            config.epochs,
            train_loss,
            validation_loss,
            validation_auc,
            validation_pe,
            time.perf_counter() - start_time,
        )
        improved = (validation_auc > best_auc) or (
            np.isclose(validation_auc, best_auc) and validation_pe < best_pe
        )
        if improved:
            best_auc = validation_auc
            best_pe = validation_pe
            best_epoch = epoch + 1
            best_threshold = threshold
            epochs_without_improvement = 0
            _save_state_dict(model, checkpoint_path)
        else:
            epochs_without_improvement += 1
        # During the high-payload curriculum the validation score is not yet
        # comparable with later epochs, so early stopping may only trigger once
        # the full payload range has been in training.
        if epoch + 1 > CURRICULUM_EPOCHS and epochs_without_improvement >= config.patience:
            break

    checkpoint: Any = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()
    validation_logits, validation_labels, _ = evaluate_logits(
        model,
        validation_loader,
        device,
        loss_function,
    )
    temperature = fit_temperature(validation_logits, validation_labels)
    elapsed = time.perf_counter() - start_time
    return TrainingResult(
        model=model,
        history=history,
        best_epoch=best_epoch,
        best_validation_auc=best_auc,
        best_validation_pe=best_pe,
        validation_threshold=best_threshold,
        temperature=temperature,
        elapsed_seconds=elapsed,
    )


def evaluate_logits(
    model: StegNetLite,
    loader: DataLoader[tuple[Tensor, Tensor]],
    device: torch.device,
    loss_function: nn.Module | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.int64], float]:
    """Collect per-image logits, labels, and mean BCE from paired examples."""
    model.eval()
    all_logits: list[NDArray[np.float64]] = []
    all_labels: list[NDArray[np.int64]] = []
    total_loss = 0.0
    count = 0
    with torch.inference_mode():
        for images, labels in loader:
            images = images.flatten(0, 1).to(device, non_blocking=device.type == "cuda")
            targets = labels.flatten().to(device, dtype=torch.float32)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                logits = model(images)
                if loss_function is not None:
                    loss = loss_function(logits, targets)
                    total_loss += float(loss.item()) * targets.numel()
            all_logits.append(logits.float().cpu().numpy().astype(np.float64))
            all_labels.append(targets.long().cpu().numpy().astype(np.int64))
            count += int(targets.numel())
    if count == 0:
        raise ValueError("Evaluation loader produced no examples.")
    average_loss = total_loss / count if loss_function is not None else 0.0
    return np.concatenate(all_logits), np.concatenate(all_labels), average_loss


def minimum_detection_error(
    labels: NDArray[np.int64],
    scores: NDArray[np.float64],
) -> tuple[float, float]:
    """Return minimum P_E and its threshold, where P_E=(P_FA+P_MD)/2."""
    if labels.ndim != 1 or scores.shape != labels.shape or not labels.size:
        raise ValueError("Labels and scores must be non-empty matching vectors.")
    if not np.isfinite(scores).all() or set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Scores must be finite and labels must contain both classes.")
    false_positive_rate, true_positive_rate, thresholds = roc_curve(labels, scores)
    errors = 0.5 * (false_positive_rate + 1.0 - true_positive_rate)
    index = int(np.argmin(errors))
    threshold = float(thresholds[index])
    if not np.isfinite(threshold):
        finite_thresholds = thresholds[np.isfinite(thresholds)]
        threshold = float(finite_thresholds[0] + 1e-12) if finite_thresholds.size else 0.5
    return float(errors[index]), threshold


def calculate_metrics(
    labels: NDArray[np.int64],
    logits: NDArray[np.float64],
    *,
    temperature: float,
    threshold: float,
    bootstrap_resamples: int = 0,
    seed: int = 1337,
) -> dict[str, object]:
    """Compute classification, P_E, TPR@1% FPR, latency-ready counts, and optional CIs."""
    if labels.ndim != 1 or logits.shape != labels.shape or not labels.size:
        raise ValueError("Labels and logits must be non-empty matching vectors.")
    if not np.isfinite(logits).all() or set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Logits must be finite and labels must include both classes.")
    probabilities = calibrated_probabilities(logits, temperature)
    predictions = (logits >= threshold).astype(np.int64)
    fpr, tpr, _ = roc_curve(labels, logits)
    low_alarm = tpr[fpr <= 0.01]
    metrics: dict[str, object] = {
        "sample_count": int(labels.size),
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(labels, logits)),
        "p_e": minimum_detection_error(labels, logits)[0],
        "tpr_at_1_percent_fpr": float(low_alarm.max()) if low_alarm.size else 0.0,
        "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
        "operating_threshold": float(threshold),
        "calibrated_mean_probability": float(probabilities.mean()),
    }
    if bootstrap_resamples > 0:
        metrics["bootstrap_95_ci"] = bootstrap_confidence_intervals(
            labels,
            logits,
            bootstrap_resamples=bootstrap_resamples,
            seed=seed,
        )
    return metrics


def bootstrap_confidence_intervals(
    labels: NDArray[np.int64],
    logits: NDArray[np.float64],
    *,
    bootstrap_resamples: int = 1000,
    seed: int = 1337,
) -> dict[str, list[float]]:
    """Estimate percentile 95% confidence intervals for AUC and P_E."""
    if labels.ndim != 1 or logits.shape != labels.shape or labels.size < 2:
        raise ValueError("Bootstrap labels and logits must be matching vectors of length >= 2.")
    if bootstrap_resamples < 1:
        raise ValueError("Bootstrap resample count must be positive.")
    rng = np.random.default_rng(seed)
    auc_values: list[float] = []
    pe_values: list[float] = []
    for _ in range(bootstrap_resamples):
        indices = rng.integers(0, labels.size, size=labels.size)
        sample_labels = labels[indices]
        if np.unique(sample_labels).size != 2:
            continue
        sample_logits = logits[indices]
        auc_values.append(float(roc_auc_score(sample_labels, sample_logits)))
        pe_values.append(minimum_detection_error(sample_labels, sample_logits)[0])
    if not auc_values:
        raise ValueError("Bootstrap resamples did not contain both classes.")
    return {
        "roc_auc": [float(value) for value in np.percentile(auc_values, [2.5, 97.5])],
        "p_e": [float(value) for value in np.percentile(pe_values, [2.5, 97.5])],
    }


def save_checkpoint(
    model: StegNetLite,
    path: Path,
    *,
    temperature: float,
    metadata: dict[str, object],
) -> None:
    """Persist a CPU state dictionary and safe, versioned CNN metadata."""
    if not 0.05 <= temperature <= 20.0:
        raise ValueError("Temperature must be in [0.05, 20].")
    checkpoint = {
        "format_version": 1,
        "truncation": model.kv_filter.truncation,
        "temperature": float(temperature),
        "model_state_dict": {
            name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()
        },
        "metadata": metadata,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    torch.save(checkpoint, temporary_path)
    temporary_path.replace(path)


def plot_training_curves(history: list[dict[str, float]], output_path: Path) -> None:
    """Save train/validation loss and validation AUC/P_E curves."""
    if not history:
        raise ValueError("Training history must contain at least one epoch.")
    epochs = [item["epoch"] for item in history]
    figure = Figure(figsize=(10, 4))
    FigureCanvasAgg(figure)
    axes = figure.subplots(1, 2)
    axes[0].plot(epochs, [item["train_loss"] for item in history], label="train")
    axes[0].plot(epochs, [item["validation_loss"] for item in history], label="validation")
    axes[0].set_title("BCE loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()
    axes[1].plot(epochs, [item["validation_auc"] for item in history], label="validation ROC-AUC")
    axes[1].plot(epochs, [item["validation_pe"] for item in history], label="validation P_E")
    axes[1].set_title("Validation selection metrics")
    axes[1].set_xlabel("Epoch")
    axes[1].legend()
    figure.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=150)
    figure.clear()


def _train_epoch(
    model: StegNetLite,
    loader: DataLoader[tuple[Tensor, Tensor]],
    optimizer: torch.optim.Optimizer,
    loss_function: nn.Module,
    scaler: torch.cuda.amp.GradScaler,
    device: torch.device,
    gradient_clip: float,
    warmup_steps: int = 0,
    base_learning_rate: float = 0.0,
) -> float:
    """Train one epoch and return its per-image mean BCE loss.

    ``warmup_steps`` ramps the learning rate linearly from near zero over the first
    steps of training (epoch 1 only); without it, AdamW's first updates at a high
    rate can push BatchNorm statistics far from where they later settle.
    """
    model.train()
    total_loss = 0.0
    image_count = 0
    for step, (images, labels) in enumerate(loader):
        if step < warmup_steps:
            for group in optimizer.param_groups:
                group["lr"] = base_learning_rate * (step + 1) / warmup_steps
        inputs = images.flatten(0, 1).to(device, non_blocking=device.type == "cuda")
        targets = labels.flatten().to(device, dtype=torch.float32)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
            logits = model(inputs)
            loss = loss_function(logits, targets)
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        nn.utils.clip_grad_norm_(model.parameters(), gradient_clip)
        scaler.step(optimizer)
        scaler.update()
        total_loss += float(loss.detach().item()) * targets.numel()
        image_count += int(targets.numel())
    if not image_count:
        raise ValueError("Training loader produced no examples.")
    return total_loss / image_count


def _group_aucs(
    logits: NDArray[np.float64],
    labels: NDArray[np.int64],
    groups: Sequence[tuple[str, int]],
) -> dict[str, float]:
    """ROC-AUC per validation condition, from the pooled logits in loader order.

    ``groups`` lists (name, image_count) in the order the conditions were
    concatenated; the loader does not shuffle, so slices line up exactly.
    """
    results: dict[str, float] = {}
    start = 0
    for name, size in groups:
        chunk_labels = labels[start : start + size]
        if size and set(np.unique(chunk_labels).tolist()) == {0, 1}:
            results[name] = float(roc_auc_score(chunk_labels, logits[start : start + size]))
        start += size
    return results


def _curriculum_payloads(epoch: int) -> tuple[float, ...]:
    """Use only higher payloads during the first eight curriculum epochs."""
    if epoch < CURRICULUM_EPOCHS:
        return tuple(bpp for bpp in TRAINING_PAYLOAD_BPP if bpp >= 0.4)
    return TRAINING_PAYLOAD_BPP


def _save_state_dict(model: StegNetLite, path: Path) -> None:
    """Atomically save the best validation-selected state for early stopping."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    torch.save(
        {
            "model_state_dict": {
                name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()
            }
        },
        temporary_path,
    )
    temporary_path.replace(path)
