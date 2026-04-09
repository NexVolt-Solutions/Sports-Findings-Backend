import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.database import engine
from app.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.routes import auth, users, matches, notifications, chat, admin, options

# ─── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify DB connection. Shutdown: dispose engine pool."""
    logger.info(
        f"Starting {settings.app_name} v{settings.app_version} "
        f"[{settings.environment}]"
    )
    try:
        async with engine.connect() as conn:
            logger.info("Database connection verified")
    except Exception as e:
        logger.error(f"Database connection failed on startup: {e}")
        raise
    yield
    logger.info("Shutting down — disposing database engine")
    await engine.dispose()


# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Sports Platform API — create, join, and discover local sports matches",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter

uploads_dir = Path(settings.uploads_dir)
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Development: allow all origins
# Production: allow only known frontend origins
ALLOWED_ORIGINS = (
    ["*"]
    if settings.debug
    else [
        # Production domains
        "https://sportfinding.com",
        "https://www.sportfinding.com",
        "https://admin.sportfinding.com",
        "https://api.sportfinding.com",
        # Flutter web development
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:52000",
        "http://localhost:5000",
        # Allow any localhost port for Flutter web testing
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:52000",
        "http://127.0.0.1:5000",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Middleware ───────────────────────────────────────────────────────────────
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


# ─── Exception Handlers ───────────────────────────────────────────────────────
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Too many requests. Please slow down and try again."},
        headers={"Retry-After": "60"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


# ─── REST Routers  (/api/v1/...) ──────────────────────────────────────────────
API_PREFIX = "/api/v1"

app.include_router(auth.router,          prefix=API_PREFIX)
app.include_router(users.router,         prefix=API_PREFIX)
app.include_router(matches.router,       prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)
app.include_router(admin.router,         prefix=API_PREFIX)
app.include_router(chat.router,          prefix=API_PREFIX)
app.include_router(options.router,       prefix=API_PREFIX)


# ─── WebSocket Routers (no /api/v1 prefix) ───────────────────────────────────
# WebSocket paths are clean, connection-level paths — no REST versioning.
#
#   WS  /ws/matches/{match_id}/chat    <- chat.ws_router
#   WS  /ws/notifications              <- notifications.ws_router

app.include_router(chat.ws_router)
app.include_router(notifications.ws_router)


logger.info(
    f"Application startup complete — {len(app.routes)} routes registered"
)

