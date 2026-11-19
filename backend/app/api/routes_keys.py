"""POST /api/keys/generate — create an Ed25519 keypair for the sender."""

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.api.deps import require_password
from app.api.limits import enforce_rate_limit
from app.api.schemas import ErrorResponse, KeyGenerateRequest, KeyGenerateResponse
from app.config import settings
from app.core.crypto import keys

router = APIRouter(tags=["Keys"])


@router.post(
    "/keys/generate",
    response_model=KeyGenerateResponse,
    dependencies=[Depends(enforce_rate_limit)],
    responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
async def generate_keys(body: KeyGenerateRequest) -> KeyGenerateResponse:
    """Generate a keypair; the private key is returned only password-encrypted.

    The server does not store either key. The client must save the encrypted
    private key and share the public key (and its fingerprint) out of band.
    """
    require_password(body.key_password, "key_password", settings.MIN_PASSWORD_LENGTH)
    return await run_in_threadpool(_generate, body.key_password)


def _generate(key_password: str) -> KeyGenerateResponse:
    """Do the CPU-bound key generation and PEM encryption off the event loop."""
    private_key, public_key = keys.generate_keypair()
    return KeyGenerateResponse(
        public_key_pem=keys.export_public_key_pem(public_key),
        private_key_pem_encrypted=keys.export_private_key_pem(private_key, key_password),
        fingerprint=keys.fingerprint(public_key),
        fingerprint_short=keys.fingerprint_short(public_key).hex(),
    )
