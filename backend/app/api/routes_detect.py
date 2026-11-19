"""POST /api/detect and /api/detect/batch — steganalysis of uploaded images."""

import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.deps import decode_image, get_suite
from app.api.errors import ApiError, api_error_from_core
from app.api.limits import enforce_rate_limit, read_upload
from app.api.schemas import (
    BatchItem,
    BatchResponse,
    DetectResponse,
    ErrorBody,
    ErrorResponse,
)
from app.config import settings
from app.core.crypto.exceptions import CryptoError
from app.core.stego.exceptions import StegoError
from app.steganalysis.service import ALL_DETECTORS, DetectorName, DetectorSuite, detect

router = APIRouter(tags=["Defender"])
OperatingPoint = Literal["balanced", "low_false_alarm"]


def parse_detectors(value: str) -> tuple[DetectorName, ...]:
    """Parse ``all`` or a CSV of ``statistical,rf,cnn``."""
    if value.strip().lower() == "all":
        return ALL_DETECTORS
    names = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    unknown = [name for name in names if name not in ALL_DETECTORS]
    if not names or unknown:
        raise ApiError(
            "BAD_REQUEST",
            "detectors must be 'all' or a comma-separated list of statistical, rf, cnn.",
            {"unknown": unknown},
        )
    return tuple(name for name in ALL_DETECTORS if name in names)


def _detect_bytes(
    suite: DetectorSuite,
    data: bytes,
    detectors: tuple[DetectorName, ...],
    operating_point: OperatingPoint,
    explain: bool,
) -> DetectResponse:
    """Decode and score one image (runs in a worker thread)."""
    image, decode_warnings = decode_image(data, settings.MAX_DETECT_PIXELS)
    result = detect(
        suite, image, detectors=detectors, operating_point=operating_point, explain=explain
    )
    if data[:3] == b"\xff\xd8\xff":
        decode_warnings.append(
            "JPEG input: compression rewrites LSBs, so LSB steganalysis is less meaningful."
        )
    result["warnings"] = decode_warnings + result["warnings"]
    return DetectResponse(
        **result,
        image_sha256=hashlib.sha256(data).hexdigest(),
        width=int(image.shape[1]),
        height=int(image.shape[0]),
        channels=1 if image.ndim == 2 else int(image.shape[2]),
    )


@router.post(
    "/detect",
    response_model=DetectResponse,
    dependencies=[Depends(enforce_rate_limit)],
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def detect_image(
    request: Request,
    image: Annotated[UploadFile, File(description="Any image to scan.")],
    detectors: Annotated[str, Form(description="'all' or CSV of statistical,rf,cnn.")] = "all",
    operating_point: Annotated[OperatingPoint, Form()] = "balanced",
    explain: Annotated[bool, Form(description="Return CNN heatmaps.")] = True,
) -> DetectResponse:
    """Scan one image and explain the verdict."""
    chosen = parse_detectors(detectors)
    data = await read_upload(image, "image")
    suite = get_suite(request)
    return await run_in_threadpool(_detect_bytes, suite, data, chosen, operating_point, explain)


@router.post(
    "/detect/batch",
    response_model=BatchResponse,
    dependencies=[Depends(enforce_rate_limit)],
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def detect_batch(
    request: Request,
    images: Annotated[list[UploadFile], File(description="Up to 20 images.")],
    detectors: Annotated[str, Form()] = "all",
    operating_point: Annotated[OperatingPoint, Form()] = "balanced",
) -> BatchResponse:
    """Scan several images without heatmaps; one bad file does not fail the batch."""
    if not images or len(images) > settings.MAX_BATCH_IMAGES:
        raise ApiError("BAD_REQUEST", f"Upload between 1 and {settings.MAX_BATCH_IMAGES} images.")
    chosen = parse_detectors(detectors)
    suite = get_suite(request)
    items: list[BatchItem] = []
    for upload in images:
        name = (upload.filename or "image")[:200]
        try:
            data = await read_upload(upload, "image")
            result = await run_in_threadpool(
                _detect_bytes, suite, data, chosen, operating_point, False
            )
            items.append(BatchItem(filename=name, result=result))
        except ApiError as exc:
            items.append(
                BatchItem(filename=name, error=ErrorBody(code=exc.code, message=exc.message))
            )
        except (StegoError, CryptoError) as exc:
            error = api_error_from_core(exc)
            items.append(
                BatchItem(filename=name, error=ErrorBody(code=error.code, message=error.message))
            )
    return BatchResponse(items=items)
