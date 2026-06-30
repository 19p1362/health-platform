"""HealthBridge Platform — Backend API Entry Point"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.auth import router as auth_router
from app.api.patients import router as patients_router
from app.api.fhir import router as fhir_router
from app.api.conversion import router as conversion_router
from app.api.consent import router as consent_router
from app.api.compliance import router as compliance_router
from app.api.admin import router as admin_router
from app.api.ingestion import router as ingestion_router
from app.api.whatsapp import router as whatsapp_router
from app.api.organizations import router as organizations_router
from app.api.exports import router as exports_router
from app.api.connectors import router as connectors_router

from app.config import settings
from app.database import init_db

# ── Logging ──
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger("healthbridge")


# ═══════════════════════════════════════════
# Lifespan (startup/shutdown)
# ═══════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init DB on startup, cleanup on shutdown."""
    logger.info(f"┌─ HealthBridge v{settings.APP_VERSION} starting ─────────────────────┐")
    logger.info(f"│ Environment: {settings.ENVIRONMENT}")
    logger.info(f"│ DB: {settings.DATABASE_URL[:50]}...")

    # Initialize database tables
    try:
        init_db()
        logger.info("│ Database tables created/verified")
    except Exception as e:
        logger.warning(f"│ DB init deferred (will create on first use): {e}")

    # Schedule DPDP compliance tasks (cron-style erasure checker, log purger)
    try:
        from app.services.dpdp_compliance import schedule_compliance_tasks
        schedule_compliance_tasks()
        logger.info("│ DPDP compliance tasks scheduled")
    except ImportError:
        logger.info("│ DPDP compliance service not yet loaded — skipping scheduler")

    logger.info("└──────────────────────────────────────────────────────┘")
    yield

    logger.info("HealthBridge shutting down...")


# ═══════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Healthcare Data Orchestration Platform — FHIR R4, DPDP 2025 Compliant",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Serve Static Files (Landing Page) ──
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def landing_page():
        return FileResponse(STATIC_DIR / "index.html")


# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════
# Middleware: DPDP Compliance Headers
# ═══════════════════════════════════════════

@app.middleware("http")
async def dpdp_compliance_headers(request: Request, call_next):
    """Add DPDP compliance and security headers to all responses."""
    response = await call_next(request)
    response.headers["X-DPDP-Compliant"] = "true"
    response.headers["X-DPDP-Version"] = "2025"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


# ═══════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "dpdp_compliant": True,
    }


# ── Register Routers ──

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(fhir_router)
app.include_router(conversion_router)
app.include_router(consent_router)
app.include_router(compliance_router)
app.include_router(admin_router)
app.include_router(ingestion_router)
app.include_router(whatsapp_router)
app.include_router(organizations_router)
app.include_router(exports_router)
app.include_router(connectors_router)


# ═══════════════════════════════════════════
# Global Exception Handlers
# ═══════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
            "incident_id": datetime.utcnow().timestamp(),
        },
    )
