"""Shared helpers for routes: image decoding with limits and detector access."""

import io
import warnings

from fastapi import Request
from PIL import Image, UnidentifiedImageError

from app.api.errors import ApiError
from app.core.stego.image_io import ImageArray, load_image
from app.steganalysis.service import DetectorSuite


def check_pixel_limit(data: bytes, max_pixels: int) -> None:
    """Read only the image header and reject images with too many pixels.

    Pillow reports width and height without decoding pixel data, so oversized
    images are refused before any large allocation happens.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as header:
                width, height = header.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ApiError("INVALID_IMAGE", "The upload is not a decodable image.") from exc
    if width * height > max_pixels:
        raise ApiError(
            "IMAGE_TOO_LARGE",
            f"Image has {width * height:,} pixels; the limit here is {max_pixels:,}.",
            {"pixels": width * height, "max_pixels": max_pixels},
        )


def decode_image(
    data: bytes, max_pixels: int, *, for_embedding: bool = False
) -> tuple[ImageArray, list[str]]:
    """Validate an upload by actually decoding it (never trusting the extension)."""
    check_pixel_limit(data, max_pixels)
    return load_image(data, for_embedding=for_embedding)


# The ``technique`` form field on /extract and /verify; zero selects the STC decoder.
TECHNIQUE_BITS: dict[str, int | None] = {"auto": None, "lsb": 1, "lsb2": 2, "stc": 0}


def get_suite(request: Request) -> DetectorSuite:
    """Return the detectors loaded at startup."""
    suite: DetectorSuite = request.app.state.detector_suite
    return suite


def require_password(value: str, field_name: str, min_length: int) -> None:
    """Enforce the minimum password length from Section 6.4."""
    if len(value) < min_length:
        raise ApiError(
            "WEAK_PASSWORD",
            f"{field_name} must be at least {min_length} characters.",
            {"field": field_name, "min_length": min_length},
        )
