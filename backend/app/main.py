"""FastAPI application entry point for StegaGuard.

The API is a thin layer: every route validates input, then calls pure
functions in ``app.core`` or ``app.steganalysis``. Nothing is written to disk.
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api import (
    routes_detect,
    routes_embed,
    routes_extract,
    routes_keys,
    routes_models,
    routes_results,
    routes_verify,
)
from app.api.errors import install_error_handlers
from app.api.limits import BodySizeLimitMiddleware, keep_uploads_in_memory
from app.api.schemas import HealthResponse
from app.config import settings
from app.steganalysis.service import load_detector_suite

logger = logging.getLogger("stegaguard.access")

# Decompression-bomb guard: Pillow refuses images above this pixel count.
Image.MAX_IMAGE_PIXELS = settings.MAX_DETECT_PIXELS
keep_uploads_in_memory()

# The API returns JSON only, so it may forbid everything else. /docs needs
# its own scripts and is excluded.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add defensive headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Attach headers after the route has produced its response."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if not request.url.path.startswith(_DOCS_PATHS):
            response.headers["Content-Security-Policy"] = _API_CSP
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log method, path, status, and latency only — never bodies or headers.

    Bodies may contain passwords, private keys, messages, or images, so they
    are deliberately absent from logs.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Time the request and write one log line."""
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "%s %s -> %d (%.0f ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Load whichever trained models exist once, at startup."""
    application.state.detector_suite = load_detector_suite(settings.MODELS_DIR)
    for warning in application.state.detector_suite.load_warnings:
        logger.warning("Model loading: %s", warning)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        description=(
            "AI-Based Image Steganalysis with Cryptographic Verification for Covert Communication"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    install_error_handlers(application)

    # Starlette runs the last-added middleware first; size limits come first.
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(AccessLogMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Retry-After"],
    )
    application.add_middleware(BodySizeLimitMiddleware)

    for module in (
        routes_keys,
        routes_embed,
        routes_extract,
        routes_verify,
        routes_detect,
        routes_models,
        routes_results,
    ):
        application.include_router(module.router, prefix=settings.API_PREFIX)

    @application.get("/api/health", tags=["System"], response_model=HealthResponse)
    @application.get("/health", tags=["System"], response_model=HealthResponse)
    async def health_check(request: Request) -> HealthResponse:
        """Report service status, version, and loaded trained models."""
        suite = getattr(request.app.state, "detector_suite", None)
        loaded = suite.loaded_model_names() if suite is not None else []
        return HealthResponse(status="ok", version=settings.VERSION, models_loaded=loaded)

    return application


app = create_app()
