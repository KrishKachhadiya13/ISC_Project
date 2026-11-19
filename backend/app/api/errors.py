"""Uniform JSON error responses: ``{"error": {"code", "message", "details"}}``."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.crypto.exceptions import CryptoError
from app.core.errors import error_code_for
from app.core.stego.exceptions import CapacityExceededError, StegoError

# HTTP status for each Section 7 error code.
STATUS_BY_CODE: dict[str, int] = {
    "STC_UNAVAILABLE": 501,
    "INVALID_IMAGE": 400,
    "UNSUPPORTED_FORMAT": 415,
    "IMAGE_TOO_LARGE": 413,
    "CAPACITY_EXCEEDED": 422,
    "WEAK_PASSWORD": 422,
    "BAD_KEY": 400,
    "KEY_MISMATCH": 422,
    "NO_HIDDEN_DATA": 422,
    "VERIFICATION_FAILED": 422,
    "DECRYPTION_FAILED": 422,
    "MODEL_UNAVAILABLE": 503,
    "RATE_LIMITED": 429,
    "BAD_REQUEST": 400,
    "NOT_FOUND": 404,
    "INTERNAL": 500,
}


class ApiError(Exception):
    """An error that maps directly to the public error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Store the code, a user-safe message, and optional details."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def error_response(error: ApiError) -> JSONResponse:
    """Render an ``ApiError`` as the standard JSON envelope."""
    return JSONResponse(
        status_code=STATUS_BY_CODE.get(error.code, 500),
        content={"error": {"code": error.code, "message": error.message, "details": error.details}},
        headers=error.headers,
    )


def api_error_from_core(error: Exception) -> ApiError:
    """Convert a core crypto/stego exception into an ``ApiError``."""
    details: dict[str, Any] = {}
    if isinstance(error, CapacityExceededError):
        details["maximum_payload_bytes"] = error.maximum_payload_bytes
    return ApiError(error_code_for(error), str(error), details)


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers so every failure uses the same envelope."""

    async def handle_api_error(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return error_response(exc)

    async def handle_core_error(_request: Request, exc: Exception) -> JSONResponse:
        return error_response(api_error_from_core(exc))

    async def handle_validation(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        # Report only field locations and messages; never echo submitted values,
        # which may be passwords or private keys.
        fields = [
            {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
            for item in exc.errors()
        ]
        return error_response(ApiError("BAD_REQUEST", "Invalid request.", {"fields": fields}))

    async def handle_http(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code = "NOT_FOUND" if exc.status_code == 404 else "BAD_REQUEST"
        return error_response(ApiError(code, str(exc.detail)))

    async def handle_unexpected(_request: Request, _exc: Exception) -> JSONResponse:
        # Deliberately generic: internal details could leak secrets or paths.
        return error_response(ApiError("INTERNAL", "An internal error occurred."))

    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(CryptoError, handle_core_error)
    app.add_exception_handler(StegoError, handle_core_error)
    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(StarletteHTTPException, handle_http)
    app.add_exception_handler(Exception, handle_unexpected)
