"""Lossless 8-bit image loading and metadata-free PNG serialization."""

from __future__ import annotations

import warnings
from io import BytesIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

from app.core.stego.exceptions import InvalidImageError, UnsupportedImageError

ImageArray = NDArray[np.uint8]
_CONVERTIBLE_MODES = {"RGBA", "LA", "P", "CMYK"}


def load_image(
    image_bytes: bytes,
    *,
    for_embedding: bool = False,
) -> tuple[ImageArray, list[str]]:
    """Decode image bytes to an 8-bit grayscale or RGB array.

    Args:
        image_bytes: Encoded image content held in memory.
        for_embedding: Reject JPEG because lossy encoding destroys embedded bits.

    Returns:
        A C-contiguous pixel array and any conversion warnings.

    Raises:
        InvalidImageError: If the input is empty, malformed, or exceeds Pillow's
            decompression-bomb threshold.
        UnsupportedImageError: If the format or bit depth is unsupported.
    """
    if not image_bytes:
        raise InvalidImageError("Image data is empty.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as source:
                source.load()
                image_format = source.format
                mode = source.mode
                if for_embedding and image_format == "JPEG":
                    raise UnsupportedImageError(
                        "JPEG is lossy; hidden bits would be destroyed. Use PNG/BMP."
                    )
                if mode.startswith("I;16") or mode in {"I", "F"}:
                    raise UnsupportedImageError("16-bit and floating-point images are unsupported.")

                conversion_warnings: list[str] = []
                if mode in {"L", "RGB"}:
                    decoded = source.copy()
                elif mode in _CONVERTIBLE_MODES:
                    decoded = source.convert("RGB")
                    if mode in {"RGBA", "LA"}:
                        conversion_warnings.append("alpha channel discarded")
                    elif mode == "P":
                        conversion_warnings.append("palette image converted to RGB")
                    else:
                        conversion_warnings.append("CMYK image converted to RGB")
                else:
                    raise UnsupportedImageError(f"Unsupported image mode: {mode}.")
                array = np.asarray(decoded, dtype=np.uint8)
    except UnsupportedImageError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImageError("Image could not be decoded safely.") from exc

    if array.ndim not in {2, 3} or (array.ndim == 3 and array.shape[2] != 3):
        raise UnsupportedImageError("Decoded image must be grayscale or RGB.")
    return np.ascontiguousarray(array), conversion_warnings


def save_png(image: ImageArray) -> bytes:
    """Serialize a grayscale or RGB uint8 array as a clean lossless PNG.

    Args:
        image: Pixel array with shape ``(H, W)`` or ``(H, W, 3)``.

    Returns:
        PNG bytes with no inherited image metadata.

    Raises:
        ValueError: If the array has an unsupported type, shape, or size.
    """
    if image.dtype != np.uint8:
        raise ValueError("Image array must use uint8 samples.")
    if image.ndim not in {2, 3} or (image.ndim == 3 and image.shape[2] != 3):
        raise ValueError("Image array must have shape (H, W) or (H, W, 3).")
    if image.shape[0] == 0 or image.shape[1] == 0:
        raise ValueError("Image dimensions must be non-empty.")

    output = BytesIO()
    Image.fromarray(np.ascontiguousarray(image)).save(output, format="PNG", compress_level=6)
    encoded = output.getvalue()
    with Image.open(BytesIO(encoded)) as reloaded:
        if not np.array_equal(np.asarray(reloaded), image):
            raise RuntimeError("PNG serialization changed image pixels.")
    return encoded
