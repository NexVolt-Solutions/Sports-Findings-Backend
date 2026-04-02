"""
app/middleware.py
----------------
Custom middleware for request logging, response time tracking,
and security headers applied to every request/response.
"""
import time
import logging
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("sports_platform.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every incoming request and outgoing response with:
    - Request ID (UUID, injected as X-Request-ID header)
    - Method, path, status code
    - Response time in milliseconds
    - User-Agent (truncated)

    Slow requests (> 500ms) are logged at WARNING level.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        # Attach request_id so route handlers can access it
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        log_level = logging.WARNING if duration_ms > 500 else logging.INFO

        logger.log(
            log_level,
            f"[{request_id}] {request.method} {request.url.path} "
            f"→ {response.status_code} ({duration_ms:.1f}ms)",
        )

        # Inject request ID into response headers for tracing
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to every response.
    These protect against common web vulnerabilities.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent browsers from MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Force HTTPS (only meaningful in production)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # Restrict referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
