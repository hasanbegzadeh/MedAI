"""RadAI Backend — FastAPI Application Entry Point."""

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.rate_limiter import limiter

settings = get_settings()

# ─── Logging Setup ────────────────────────────────────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level)
    )
)
logger = structlog.get_logger()

# ─── Rate Limiter ─────────────────────────────────────────────────────────────


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


# ─── Lifespan (startup / shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RadAI backend starting", env=settings.environment)

    # ── CUDA availability check ──────────────────────────────────────────────
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            free_vram = torch.cuda.mem_get_info()[0] / 1e9
            logger.info("CUDA available", gpu=gpu_name, free_vram_gb=f"{free_vram:.1f}")
        else:
            logger.warning(
                "CUDA not available — AI inference will use CPU (very slow). "
                "Check NVIDIA drivers and CUDA toolkit installation."
            )
    except ImportError:
        logger.warning("PyTorch not installed — GPU scheduling disabled")

    yield
    logger.info("RadAI backend shutting down")


# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="RadAI API",
    description=(
        "AI-powered radiology assistant backend. "
        "All AI findings require physician review and confirmation."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware, limiter=limiter)
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ─── CORS ────────────────────────────────────────────────────────────────────
# Includes Docker-internal OHIF hostnames so CORS works inside Docker network
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://ohif:80",
        "http://radai-ohif:80",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ─── Audit Middleware (Medical AI compliance) ────────────────────────────────
@app.middleware("http")
async def audit_ai_operations(request: Request, call_next):
    """Log all AI and report operations to structured log for audit trail.

    Medical AI requires tracking: who ran what, when, and the outcome.
    This middleware captures all /api/v1/ai and /api/v1/reports calls.
    """
    response = await call_next(request)
    if request.url.path.startswith(("/api/v1/ai", "/api/v1/reports")):
        logger.info(
            "audit_ai_operation",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            client_ip=request.client.host if request.client else "unknown",
        )
    return response


# ─── Routers ─────────────────────────────────────────────────────────────────
from app.api import ai, auth, reports, studies, voice
from app.websocket import router as ws_router

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(studies.router, prefix="/api/v1/studies", tags=["studies"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(voice.router, prefix="/api/v1/voice", tags=["voice"])
app.include_router(ws_router, prefix="/ws", tags=["websocket"])


# ─── Health Check (tests DB + Redis + Ollama connectivity) ───────────────────
@app.get("/health", tags=["health"])
async def health() -> dict:
    """Comprehensive health check — used by Docker health checks and load balancers.

    Tests connectivity to PostgreSQL, Redis, and Ollama. Returns 'degraded'
    status if any dependency is unreachable.
    """
    checks: dict[str, str] = {"api": "ok"}

    # Check PostgreSQL
    try:
        from sqlalchemy import text
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
        logger.warning("Health check: database unreachable", error=str(exc))

    # Check Redis
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.redis_url, socket_timeout=3)
        r.ping()
        r.close()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
        logger.warning("Health check: Redis unreachable", error=str(exc))

    # Check Ollama
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_url}/api/tags")
            resp.raise_for_status()
        checks["ollama"] = "ok"
    except Exception:
        checks["ollama"] = "unreachable"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "version": "0.1.0", "checks": checks}


# ─── Global Exception Handler ────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    logger.error("Unhandled exception", exc_info=exc, path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check server logs."},
    )
