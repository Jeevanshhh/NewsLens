"""NewsLens backend application entrypoint (FastAPI).

Run (from the `backend/` directory):
    uvicorn app.main:app --reload

This is the Phase 1 foundation: app factory, env-driven config, structured
logging, CORS, a versioned API router and a health endpoint. Search, DB,
auth, analytics and exports are added in later phases.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger, request_id_var
from app.database.connection import init_db

logger = get_logger("app.main")

# Baseline hardening headers sent on every API response. The CSP is scoped to
# what a JSON API + its (dev-only) Swagger UI actually need, and deliberately
# forbids framing to blunt clickjacking.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self'"
    ),
}


def _init_error_monitoring(settings: Settings) -> None:
    """Best-effort error-monitoring hook. No-op unless configured.

    We deliberately avoid a hard dependency on any vendor SDK: the package is
    only imported and initialised when a DSN is configured *and* installed,
    otherwise we log that monitoring is off. Nothing here leaks the DSN.
    """
    if not settings.sentry_dsn:
        logger.info("Error monitoring disabled (no SENTRY_DSN configured).")
        return
    try:
        import sentry_sdk  # type: ignore
    except Exception:  # noqa: BLE001 - optional integration, never fatal
        logger.warning("SENTRY_DSN set but sentry-sdk is unavailable; monitoring stays off.")
        return
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.app_env)  # pragma: no cover
    logger.info("Error monitoring initialised.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(
        "DEBUG" if not settings.is_production else "INFO",
        json_output=settings.log_json or settings.is_production,
    )
    _init_error_monitoring(settings)

    # Fail closed in production on insecure configuration rather than booting
    # a deployment that signs tokens with a default key or allows credentialed
    # wildcard CORS. Nothing is ever logged that reveals secret values.
    if settings.is_production:
        fatal = settings.production_safety_errors()
        if fatal:
            raise RuntimeError("Refusing to start in production: " + " ".join(fatal))

    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)

    # Surface insecure defaults loudly in production, without ever logging
    # the secret values themselves.
    for warning in settings.unsafe_default_warnings():
        level = logger.error if settings.is_production else logger.warning
        level("SECURITY: %s", warning)

    if not settings.gnews_configured:
        logger.warning("GNews API key not configured (placeholder in use).")
    if not settings.newsdata_configured:
        logger.warning("NewsData API key not configured (placeholder in use).")

    # Ensure tables exist (dev/SQLite). Alembic manages schema in production.
    init_db()
    logger.info("Database initialised.")

    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Multi-source news intelligence & reporting platform API.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    max_body = settings.max_body_bytes

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # Correlate every log line for this request; honour an inbound id so it
        # chains across proxies/services, else mint one.
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        ctx = request_id_var.set(rid)
        try:
            # Defence-in-depth size guard on the declared Content-Length
            # (auth/search bodies are tiny); a real gateway enforces the hard cap.
            if request.method in ("POST", "PUT", "PATCH"):
                length = request.headers.get("content-length")
                if length and length.isdigit() and int(length) > max_body:
                    response = JSONResponse({"detail": "request body too large"}, status_code=413)
                else:
                    response = await call_next(request)
            else:
                response = await call_next(request)
        finally:
            request_id_var.reset(ctx)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Log the real cause server-side, return a generic, non-leaking body.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "internal server error"}, status_code=500)

    app.include_router(api_router, prefix="/api")

    @app.get("/", tags=["health"], summary="API index")
    def index() -> dict:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "health": "/api/health",
        }

    return app


app = create_app()
