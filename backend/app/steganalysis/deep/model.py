"""StegNet-Lite CNN architecture for grayscale image steganalysis."""

from typing import cast

from torch import Tensor, nn

from app.steganalysis.deep.filters import KVFilter


class ResidualBlock(nn.Module):
    """Two-convolution residual block with an optional channel projection."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        """Build a residual block that preserves spatial resolution."""
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.skip = (
            nn.Identity()
            if in_channels == out_channels
            else nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, bias=False),
                nn.BatchNorm2d(out_channels),
            )
        )
        self.activation = nn.ReLU(inplace=True)

    def forward(self, inputs: Tensor) -> Tensor:
        """Apply the residual path and nonlinearity."""
        residual = self.skip(inputs)
        output = self.activation(self.bn1(self.conv1(inputs)))
        output = self.bn2(self.conv2(output))
        return cast(Tensor, self.activation(output + residual))


class DownsampleBlock(nn.Module):
    """Increase feature channels and downsample with average pooling."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        """Build a convolutional feature block followed by 2× average pooling."""
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False)
        self.bn = nn.BatchNorm2d(out_channels)
        self.activation = nn.ReLU(inplace=True)
        self.pool = nn.AvgPool2d(kernel_size=2, stride=2)

    def forward(self, inputs: Tensor) -> Tensor:
        """Extract a feature map and halve its spatial dimensions."""
        return cast(Tensor, self.pool(self.activation(self.bn(self.conv(inputs)))))


class StegNetLite(nn.Module):
    """Residual-first six-stage CNN with a fixed KV input residual filter."""

    def __init__(self, truncation: float = 3.0) -> None:
        """Create the under-2M-parameter StegNet-Lite classifier."""
        super().__init__()
        self.kv_filter = KVFilter(truncation)
        self.stem = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
        )
        self.stage1 = ResidualBlock(16, 16)
        self.stage2 = ResidualBlock(16, 16)
        self.stage3 = ResidualBlock(16, 16)
        self.stage4 = DownsampleBlock(16, 32)
        self.stage5 = DownsampleBlock(32, 64)
        self.stage6 = DownsampleBlock(64, 128)
        self.global_pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Linear(128, 1)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        """Initialize trainable convolutions with Kaiming weights."""
        for module in self.modules():
            if isinstance(module, nn.Conv2d) and module.weight.requires_grad:
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(module, nn.BatchNorm2d):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.zeros_(self.classifier.bias)

    def forward(self, image: Tensor) -> Tensor:
        """Return one steganalysis logit per normalized grayscale image."""
        if image.ndim != 4 or image.shape[1] != 1:
            raise ValueError("StegNet-Lite expects input shaped (batch, 1, height, width).")
        if image.shape[2] < 32 or image.shape[3] < 32:
            raise ValueError("StegNet-Lite input dimensions must be at least 32 pixels.")
        output = self.kv_filter(image)
        output = self.stem(output)
        output = self.stage1(output)
        output = self.stage2(output)
        output = self.stage3(output)
        output = self.stage4(output)
        output = self.stage5(output)
        output = self.stage6(output)
        output = self.global_pool(output).flatten(1)
        return cast(Tensor, self.classifier(output).squeeze(1))

    @property
    def last_conv_layer(self) -> nn.Conv2d:
        """Return the last convolutional layer used for Grad-CAM."""
        return self.stage6.conv

    def trainable_parameter_count(self) -> int:
        """Count parameters that receive optimizer updates."""
        return sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)


def build_model(truncation: float = 3.0) -> StegNetLite:
    """Create StegNet-Lite and reject accidental architecture growth."""
    model = StegNetLite(truncation=truncation)
    if model.trainable_parameter_count() >= 2_000_000:
        raise RuntimeError("StegNet-Lite must remain below two million trainable parameters.")
    return model
