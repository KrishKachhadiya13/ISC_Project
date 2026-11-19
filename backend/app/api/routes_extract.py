"""POST /api/extract — recover a message only after the signature verifies."""

import base64
from typing import Annotated, Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.deps import TECHNIQUE_BITS, check_pixel_limit
from app.api.errors import ApiError
from app.api.limits import enforce_rate_limit, read_upload
from app.api.routes_embed import sanitize_filename
from app.api.schemas import ErrorResponse, ExtractResponse, Stage
from app.config import settings
from app.core import pipeline
from app.core.crypto import keys
from app.core.crypto.exceptions import CryptoError

router = APIRouter(tags=["Receiver"])


def _technique_name(bits_per_sample: int | None) -> Literal["lsb", "lsb2", "stc"] | None:
    """Name the decoder that found the packet (None when extraction failed)."""
    if bits_per_sample == 1:
        return "lsb"
    if bits_per_sample == 2:
        return "lsb2"
    if bits_per_sample == 0:
        return "stc"
    return None


def candidate_modes(mode: str | None) -> list[Literal["keyed", "sequential"]]:
    """Placement modes to try: both for ``auto`` (keyed first), otherwise just the one asked for."""
    if mode == "keyed":
        return ["keyed"]
    if mode == "sequential":
        return ["sequential"]
    return ["keyed", "sequential"]


def _progress(result: pipeline.ReceiverResult) -> int:
    """How many stages passed; used to pick the most informative failed attempt."""
    return sum(1 for stage in result.stages if stage.status == "passed")


def load_public_key(pem: str) -> Ed25519PublicKey:
    """Parse the receiver-supplied public key or raise BAD_KEY."""
    try:
        return keys.load_public_key_pem(pem)
    except CryptoError as exc:
        raise ApiError("BAD_KEY", "The public key is not a valid Ed25519 PEM.") from exc


@router.post(
    "/extract",
    response_model=ExtractResponse,
    dependencies=[Depends(enforce_rate_limit)],
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def extract_message(
    image: Annotated[UploadFile, File(description="Stego PNG to read.")],
    password: Annotated[str, Form(description="Message password.")],
    public_key_pem: Annotated[str, Form(description="Sender's public key PEM.")],
    mode: Annotated[
        Literal["auto", "keyed", "sequential"],
        Form(description="Where the bits sit: auto-detect, keyed scatter, or in order."),
    ] = "auto",
    technique: Annotated[
        Literal["auto", "lsb", "lsb2", "stc"],
        Form(description="Decoder: auto-detect, 1-bit LSB, 2-LSB, or STC."),
    ] = "auto",
    stego_passphrase: Annotated[str | None, Form()] = None,
) -> ExtractResponse:
    """Run the ordered receiver stages; content is returned only if all pass.

    Stage failures (wrong key, tampering, wrong password) are reported inside
    a normal 200 response so the UI can show exactly which stage stopped.
    """
    public_key = load_public_key(public_key_pem)
    image_bytes = await read_upload(image, "image")
    # A stego image can never exceed the embedding limit, so use it here too.
    check_pixel_limit(image_bytes, settings.MAX_EMBED_PIXELS)
    # The sender UI defaults the stego passphrase to the message password.
    passphrase = stego_passphrase or password

    def attempt_all() -> tuple[pipeline.ReceiverResult, Literal["keyed", "sequential"]]:
        best: tuple[pipeline.ReceiverResult, Literal["keyed", "sequential"]] | None = None
        for candidate in candidate_modes(mode):
            outcome = pipeline.receiver_pipeline(
                image_bytes,
                password,
                public_key,
                mode=candidate,
                stego_passphrase=passphrase,
                bits_per_sample=TECHNIQUE_BITS[technique],
            )
            if outcome.verified:
                return outcome, candidate
            # Keep the attempt that got furthest so the failure shown is the useful one.
            if best is None or _progress(outcome) > _progress(best[0]):
                best = (outcome, candidate)
        assert best is not None
        return best

    result, used_mode = await run_in_threadpool(attempt_all)
    response = ExtractResponse(
        stages=[
            Stage(name=s.name, status=s.status, detail=s.detail, code=s.code) for s in result.stages
        ],
        verified=result.verified,
        technique=_technique_name(result.bits_per_sample),
        mode=used_mode if result.verified else None,
        supplied_key_fingerprint=keys.fingerprint(public_key),
    )
    # Content fields are filled only from a fully verified result.
    if result.verified and result.payload is not None:
        if result.payload.is_file:
            response.file_base64 = base64.b64encode(result.payload.data).decode("ascii")
            response.filename = sanitize_filename(result.payload.filename or "file")
        else:
            response.plaintext = result.plaintext
    return response
