"""POST /api/verify — the three independent integrity checks of Section 6.6."""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.deps import TECHNIQUE_BITS, check_pixel_limit
from app.api.errors import ApiError
from app.api.limits import enforce_rate_limit, read_upload
from app.api.routes_extract import candidate_modes, load_public_key
from app.api.schemas import ErrorResponse, VerifyResponse
from app.config import settings
from app.core import pipeline

router = APIRouter(tags=["Receiver"])
_MAX_MANIFEST_CHARACTERS = 64 * 1024


@router.post(
    "/verify",
    response_model=VerifyResponse,
    dependencies=[Depends(enforce_rate_limit)],
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def verify_image(
    image: Annotated[UploadFile, File(description="Image to check.")],
    manifest: Annotated[str, Form(description="Signed manifest JSON text.")],
    public_key_pem: Annotated[str, Form(description="Sender's public key PEM.")],
    mode: Annotated[Literal["auto", "keyed", "sequential"] | None, Form()] = None,
    technique: Annotated[Literal["auto", "lsb", "lsb2", "stc"], Form()] = "auto",
    stego_passphrase: Annotated[str | None, Form()] = None,
) -> VerifyResponse:
    """Check (A) pixel hash, (B) manifest signature, (C) embedded packet signature.

    Check C runs only when ``mode`` is given (and, for keyed mode, a stego
    passphrase), because the packet cannot be located otherwise.
    """
    manifest_data = _parse_manifest(manifest)
    public_key = load_public_key(public_key_pem)
    image_bytes = await read_upload(image, "image")
    check_pixel_limit(image_bytes, settings.MAX_EMBED_PIXELS)
    # Keyed placement cannot be located without the stego passphrase, so only try it with one.
    modes = (
        [m for m in candidate_modes(mode) if m == "sequential" or stego_passphrase] if mode else []
    )
    effective_mode = modes[0] if modes else None

    def check_all() -> dict[str, Any]:
        outcome: dict[str, Any] = {}
        for candidate in modes or [None]:
            outcome = pipeline.verify_pipeline(
                image_bytes,
                manifest_data,
                public_key,
                mode=candidate,
                stego_passphrase=stego_passphrase or None,
                bits_per_sample=TECHNIQUE_BITS[technique],
            )
            payload_check = outcome["checks"].get("payload_signature")
            if payload_check is not None and payload_check.get("ok"):
                break
        return outcome

    result = await run_in_threadpool(check_all)
    if mode in ("keyed", "auto") and effective_mode is None:
        result["checks"]["payload_signature"]["detail"] = (
            "Not checked: keyed mode needs the stego passphrase."
        )
    if mode is None:
        result["checks"]["payload_signature"] = None
    return VerifyResponse.model_validate(result)


def _parse_manifest(text: str) -> dict[str, Any]:
    """Parse the manifest JSON, rejecting oversized or non-object input."""
    if len(text) > _MAX_MANIFEST_CHARACTERS:
        raise ApiError("BAD_REQUEST", "Manifest is too large.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ApiError("BAD_REQUEST", "Manifest is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ApiError("BAD_REQUEST", "Manifest must be a JSON object.")
    return data
