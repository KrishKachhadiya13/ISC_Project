"""FastAPI main application entry point for StegaGuard."""

from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing standard defensive HTTP security headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        description="AI-Based Image Steganalysis with Cryptographic Verification for Covert Communication",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Middleware
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @application.get("/api/health", tags=["System"])
    @application.get("/health", tags=["System"])
    async def health_check() -> dict[str, Any]:
        """Health check endpoint indicating service status, version, and loaded models.

        Returns:
            Dict containing status, version, and loaded models list.
        """
        loaded_models: list[str] = []
        return {
            "status": "ok",
            "version": settings.VERSION,
            "models_loaded": loaded_models,
        }

    return application


app = create_app()
