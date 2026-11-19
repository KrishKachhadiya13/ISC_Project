"""Temperature scaling for CNN logits using the validation split only."""

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn
from torch.nn import functional as functional


def fit_temperature(
    logits: NDArray[np.float64] | Tensor,
    labels: NDArray[np.int64] | Tensor,
    max_iterations: int = 50,
) -> float:
    """Fit a positive scalar temperature by minimizing validation BCE.

    Args:
        logits: One-dimensional, uncalibrated validation logits.
        labels: Binary validation labels encoded as zero or one.
        max_iterations: Maximum LBFGS optimization steps.

    Returns:
        A finite temperature clamped to ``[0.05, 20]``.
    """
    logit_tensor = torch.as_tensor(logits, dtype=torch.float64).reshape(-1)
    label_tensor = torch.as_tensor(labels, dtype=torch.float64).reshape(-1)
    if logit_tensor.numel() == 0 or logit_tensor.shape != label_tensor.shape:
        raise ValueError("Validation logits and labels must be non-empty matching vectors.")
    if not torch.isfinite(logit_tensor).all() or not torch.isfinite(label_tensor).all():
        raise ValueError("Validation logits and labels must be finite.")
    if not torch.all((label_tensor == 0) | (label_tensor == 1)):
        raise ValueError("Validation labels must contain only zero and one.")
    if not bool(torch.any(label_tensor == 0) and torch.any(label_tensor == 1)):
        raise ValueError("Validation labels must include both classes.")
    if max_iterations < 1:
        raise ValueError("Maximum calibration iterations must be positive.")

    log_temperature = nn.Parameter(torch.zeros((), dtype=torch.float64))
    optimizer = torch.optim.LBFGS([log_temperature], max_iter=max_iterations)

    def closure() -> Tensor:
        optimizer.zero_grad()
        temperature = torch.exp(log_temperature).clamp(0.05, 20.0)
        loss = functional.binary_cross_entropy_with_logits(
            logit_tensor / temperature,
            label_tensor,
        )
        loss.backward()  # type: ignore[no-untyped-call]
        return loss

    optimizer.step(closure)  # type: ignore[no-untyped-call]
    return float(torch.exp(log_temperature.detach()).clamp(0.05, 20.0).item())


def calibrated_probabilities(
    logits: NDArray[np.float64] | Tensor,
    temperature: float,
) -> NDArray[np.float64]:
    """Convert logits to probabilities after applying a validated temperature."""
    if not np.isfinite(temperature) or not 0.05 <= temperature <= 20.0:
        raise ValueError("Temperature must be finite and in [0.05, 20].")
    values = np.asarray(torch.as_tensor(logits, dtype=torch.float64).cpu(), dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("Logits must be finite.")
    scaled = np.clip(values / temperature, -80.0, 80.0)
    probabilities: NDArray[np.float64] = (1.0 / (1.0 + np.exp(-scaled))).astype(np.float64)
    return probabilities
