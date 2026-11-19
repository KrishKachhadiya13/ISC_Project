"""POST /api/embed — encrypt, sign, and hide a message in a cover image."""

import base64
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.deps import decode_image, require_password
from app.api.errors import ApiError
from app.api.limits import enforce_rate_limit, read_upload
from app.api.schemas import EmbedMetrics, EmbedResponse, ErrorResponse
from app.config import settings
from app.core import pipeline
from app.core.crypto import keys
from app.core.crypto.exceptions import CryptoError

router = APIRouter(tags=["Sender"])
_UNSAFE_FILENAME_CHARACTERS = re.compile(r"[^A-Za-z0-9._ -]")


@router.post(
    "/embed",
    response_model=EmbedResponse,
    dependencies=[Depends(enforce_rate_limit)],
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
async def embed_message(
    cover: Annotated[UploadFile, File(description="Lossless cover image (PNG/BMP/PGM).")],
    password: Annotated[str, Form(description="Message encryption password (>= 8 chars).")],
    private_key_pem: Annotated[str, Form(description="Password-encrypted PKCS#8 PEM.")],
    key_password: Annotated[str, Form(description="Password that unlocks the private key.")],
    method: Annotated[
        Literal["lsb_replace", "lsb_match", "lsb2_replace", "suniward", "hill"], Form()
    ] = "lsb_replace",
    mode: Annotated[Literal["keyed", "sequential"], Form()] = "keyed",
    message: Annotated[str | None, Form(description="Text message.")] = None,
    message_file: Annotated[UploadFile | None, File(description="File to hide instead.")] = None,
    stego_passphrase: Annotated[str | None, Form()] = None,
) -> EmbedResponse:
    """Run the sender pipeline entirely in memory and return the exact PNG bytes."""
    require_password(password, "password", settings.MIN_PASSWORD_LENGTH)
    passphrase = stego_passphrase or None
    if passphrase is not None and mode == "keyed":
        require_password(passphrase, "stego_passphrase", settings.MIN_PASSWORD_LENGTH)
    content, is_file, filename = await _message_content(message, message_file)
    cover_bytes = await read_upload(cover, "cover")
    # Decode once here so limits and JPEG rejection give clear errors early.
    _array, _warnings = decode_image(cover_bytes, settings.MAX_EMBED_PIXELS, for_embedding=True)
    try:
        signing_key = keys.load_private_key_pem(private_key_pem, key_password)
    except CryptoError as exc:
        raise ApiError(
            "BAD_KEY", "The private key could not be unlocked with that key password."
        ) from exc

    stego_png, manifest, metrics, diff_png, warnings = await run_in_threadpool(
        lambda: pipeline.sender_pipeline(
            cover_bytes,
            content,
            password,
            signing_key,
            key_password,
            method=method,
            mode=mode,
            stego_passphrase=passphrase,
            is_file=is_file,
            filename=filename,
        )
    )
    return EmbedResponse(
        stego_png_base64=base64.b64encode(stego_png).decode("ascii"),
        manifest=manifest,
        metrics=EmbedMetrics(**metrics),  # type: ignore[arg-type]
        diff_png_base64=base64.b64encode(diff_png).decode("ascii"),
        warnings=warnings,
        sender_fingerprint=keys.fingerprint(signing_key.public_key()),
    )


async def _message_content(
    message: str | None, message_file: UploadFile | None
) -> tuple[str | bytes, bool, str | None]:
    """Return exactly one of the text message or the uploaded file."""
    has_file = message_file is not None and bool(message_file.filename)
    if has_file == (message is not None and message != ""):
        raise ApiError("BAD_REQUEST", "Provide exactly one of 'message' or 'message_file'.")
    if has_file and message_file is not None:
        data = await read_upload(message_file, "message_file")
        return data, True, sanitize_filename(message_file.filename or "file")
    return message or "", False, None


def sanitize_filename(name: str) -> str:
    """Keep a short, plain filename; path parts and odd characters are removed."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _UNSAFE_FILENAME_CHARACTERS.sub("_", base).strip(" .")
    return (cleaned or "file")[:100]
