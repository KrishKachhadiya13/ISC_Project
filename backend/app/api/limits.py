"""Request limits: per-IP rate limiting, body-size caps, and in-memory uploads.

The rate limiter is a small in-process sliding window rather than a library
so that its behaviour is easy to explain and test. It is per worker process;
a multi-instance deployment would need a shared store such as Redis.
"""

import threading
import time
from collections import deque

from fastapi import Request, UploadFile
from starlette.formparsers import MultiPartParser
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import ApiError, error_response
from app.config import settings

# Room for multipart boundaries and text fields on top of the file limit.
_MULTIPART_OVERHEAD_BYTES = 256 * 1024


def keep_uploads_in_memory() -> None:
    """Stop Starlette from spooling large uploads to temporary files on disk.

    Starlette keeps an upload in memory only up to ``spool_max_size`` (1 MB by
    default) and then writes it to a temp file. The stateless-server rule
    forbids writing uploads to disk, so the threshold is raised above the
    request-size cap, which is enforced before parsing.
    """
    # Use the largest allowed request body so no single part can ever spill.
    MultiPartParser.spool_max_size = max_request_bytes("/detect/batch")
    # Text fields (such as PEM keys) are small; keep the 1 MB per-field default.


def max_request_bytes(path: str) -> int:
    """Return the body-size cap for a path (batch detect allows 20 files)."""
    files = settings.MAX_BATCH_IMAGES if path.endswith("/detect/batch") else 2
    return settings.MAX_UPLOAD_SIZE_BYTES * files + _MULTIPART_OVERHEAD_BYTES


class BodySizeLimitMiddleware:
    """Reject oversized bodies before any parsing, using Content-Length and a counter."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the downstream ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enforce the cap on declared and actually received body bytes."""
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        limit = max_request_bytes(scope["path"])
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _reject_too_large(scope, receive, send, limit)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise ApiError("IMAGE_TOO_LARGE", _too_large_message(limit))
            return message

        await self.app(scope, counting_receive, send)


async def _reject_too_large(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
    """Send the IMAGE_TOO_LARGE envelope without reading the body."""
    response = error_response(ApiError("IMAGE_TOO_LARGE", _too_large_message(limit)))
    await response(scope, receive, send)


def _too_large_message(limit: int) -> str:
    """Explain the size cap in megabytes."""
    return f"Request body exceeds the {limit / (1024 * 1024):.1f} MB limit."


async def read_upload(upload: UploadFile, field_name: str) -> bytes:
    """Read one uploaded file fully into memory, enforcing the per-file cap."""
    data = await upload.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
    if len(data) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise ApiError(
            "IMAGE_TOO_LARGE",
            f"{field_name} exceeds the {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB limit.",
        )
    if not data:
        raise ApiError("INVALID_IMAGE", f"{field_name} is empty.")
    return data


class SlidingWindowRateLimiter:
    """Allow at most ``limit`` requests per client in any ``window`` seconds."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        """Create an empty limiter."""
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, client: str, now: float | None = None) -> float | None:
        """Record a request; return seconds to wait if the client is over the limit."""
        current = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(client, deque())
            while hits and current - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(0.0, self.window_seconds - (current - hits[0]))
            hits.append(current)
            self._prune(current)
            return None

    def reset(self) -> None:
        """Forget all clients (used by tests and on configuration changes)."""
        with self._lock:
            self._hits.clear()

    def _prune(self, current: float) -> None:
        """Drop idle clients so memory does not grow with unique IPs."""
        if len(self._hits) < 10_000:
            return
        idle = [
            key
            for key, hits in self._hits.items()
            if not hits or current - hits[-1] >= self.window_seconds
        ]
        for key in idle:
            del self._hits[key]


def parse_rate(rate: str) -> tuple[int, float]:
    """Parse ``"30/minute"`` style strings into (count, seconds)."""
    count_text, _, unit = rate.partition("/")
    seconds = {"second": 1.0, "minute": 60.0, "hour": 3600.0}.get(unit.strip().lower())
    if not count_text.strip().isdigit() or seconds is None or int(count_text) < 1:
        raise ValueError(f"Invalid rate limit: {rate!r}")
    return int(count_text), seconds


_count, _seconds = parse_rate(settings.RATE_LIMIT_DEFAULT)
rate_limiter = SlidingWindowRateLimiter(_count, _seconds)


async def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency applied to every POST route."""
    client = request.client.host if request.client else "unknown"
    retry_after = rate_limiter.check(client)
    if retry_after is not None:
        seconds = max(1, int(retry_after + 0.999))
        raise ApiError(
            "RATE_LIMITED",
            "Too many requests. Please wait and try again.",
            {"retry_after_seconds": seconds},
            headers={"Retry-After": str(seconds)},
        )
