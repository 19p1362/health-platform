"""HealthBridge Platform — Configuration Management"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Application
    APP_NAME: str = "HealthBridge API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = ""
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./healthbridge.db"
    DATABASE_SYNC_URL: str | None = None

    # Redis
    REDIS_URL: str | None = None

    # JWT
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    # Encryption (Fernet 32-byte key, base64-encoded)
    ENCRYPTION_KEY: str | None = None

    # ABHA (Ayushman Bharat Health Account)
    ABHA_API_BASE_URL: str = "https://sandbox.abdm.gov.in"
    ABHA_CLIENT_ID: str = ""
    ABHA_CLIENT_SECRET: str = ""

    # Aadhaar eKYC
    AADHAAR_EKYC_ENABLED: bool = False
    AADHAAR_API_BASE_URL: str = "https://sandbox.uidai.gov.in"
    AADHAAR_LICENSE_KEY: str = ""
    AADHAAR_ASA_ID: str = ""
    AADHAAR_SUB_ASA_ID: str = ""

    # Consent Manager
    CONSENT_MANAGER_ENABLED: bool = False
    CONSENT_MANAGER_API_URL: str = ""

    # Notifications
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None

    # FHIR
    FHIR_SERVER_BASE: str = "http://localhost:8080/fhir"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_PER_HOUR: int = 1000

    # DPDP Compliance
    DPDP_BREACH_NOTIFICATION_ENABLED: bool = True
    DPDP_RETENTION_DAYS: int = 365  # 1 year minimum log retention
    DPDP_ERASURE_NOTIFICATION_HOURS: int = 48
    DPDP_GRIEVANCE_SLA_DAYS: int = 90
    DPDP_CLINICAL_RETENTION_YEARS: int = 3  # Clinical Establishments Act

    # Security
    PASSWORD_MIN_LENGTH: int = 12
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    SESSION_TIMEOUT_MINUTES: int = 30

    # Document Ingestion (OCR + AI)
    UPLOAD_DIR: str = "data/uploads"
    AI_EXTRACTION_API_URL: str = "https://api.openai.com/v1/chat/completions"
    AI_EXTRACTION_API_KEY: str = ""  # OpenAI / any OpenAI-compatible API key
    AI_EXTRACTION_MODEL: str = "gpt-4o-mini"  # cheap & fast for extraction
    OCR_ENABLED: bool = True
    MAX_UPLOAD_SIZE_MB: int = 10

    # WhatsApp Webhook (Meta Cloud API)
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "healthbridge-verify-2026"

    # Twilio WhatsApp
    TWILIO_WHATSAPP_NUMBER: str = ""

    model_config = {"env_file": ".env", "case_sensitive": True}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def database_sync_url_fallback(self) -> str:
        return self.DATABASE_SYNC_URL or self.DATABASE_URL.replace(
            "+aiosqlite", ""
        ).replace("+asyncpg", "")


settings = Settings()

# ── Startup Validation ──
if settings.ENVIRONMENT == "production":
    if not settings.SECRET_KEY or settings.SECRET_KEY == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY must be set to a secure random value in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    if not settings.JWT_SECRET or settings.JWT_SECRET == "change-me-in-production":
        raise RuntimeError(
            "JWT_SECRET must be set to a secure random value in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )

# ── Paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
