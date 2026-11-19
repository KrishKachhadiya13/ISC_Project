"""Fixed high-pass residual filters used by StegNet-Lite."""

import torch
from torch import Tensor, nn

KV_KERNEL = (
    torch.tensor(
        [
            [-1, 2, -2, 2, -1],
            [2, -6, 8, -6, 2],
            [-2, 8, -12, 8, -2],
            [2, -6, 8, -6, 2],
            [-1, 2, -2, 2, -1],
        ],
        dtype=torch.float32,
    )
    / 12.0
)


class KVFilter(nn.Module):
    """Apply the fixed 5×5 KV high-pass kernel and truncate its residual."""

    def __init__(self, truncation: float = 3.0) -> None:
        """Create a non-trainable convolution with a validated residual bound."""
        super().__init__()
        if truncation <= 0:
            raise ValueError("Residual truncation must be positive.")
        self.truncation = float(truncation)
        self.conv = nn.Conv2d(1, 1, kernel_size=5, padding=2, bias=False)
        with torch.no_grad():
            self.conv.weight.copy_(KV_KERNEL.view(1, 1, 5, 5))
        self.conv.weight.requires_grad_(False)

    def forward(self, image: Tensor) -> Tensor:
        """Return a clamped, spatially aligned high-pass residual."""
        return torch.clamp(
            self.conv(image),
            min=-self.truncation,
            max=self.truncation,
        )
