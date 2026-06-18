"""
Healthcare Orchestra — Root Configuration.

Provides the central config object used by the dashboard, orchestrator,
and all agents. Reads from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class _Config:
    """Application-level configuration (singleton)."""

    # -- HealthBridge API ----------------------------------------------------
    HEALTHBRIDGE_API_URL: str = os.getenv(
        "HEALTHBRIDGE_API_URL", "http://localhost:8080"
    )

    # -- Database -----------------------------------------------------------
    DB_PATH: Path = Path(
        os.getenv("DB_PATH", str(Path(__file__).parent / "healthcare_orchestra.db"))
    )

    # -- Agent configuration ------------------------------------------------
    # name -> enabled (bool)
    AGENTS: dict[str, bool] = {
        "patient_intake": True,
        "medication_adherence": True,
        "follow_up": True,
        "appointment": True,
        "risk_prediction": True,
        "family_care": True,
        "voice_care": True,
        "pharmacy": True,
        "lab": True,
        "insurance": True,
    }

    # name -> run interval in minutes
    AGENT_INTERVALS: dict[str, int] = {
        "patient_intake": 60,
        "medication_adherence": 15,
        "follow_up": 30,
        "appointment": 30,
        "risk_prediction": 60,
        "family_care": 10080,  # weekly
        "voice_care": 60,
        "pharmacy": 60,
        "lab": 30,
        "insurance": 1440,  # daily
    }

    # -- Dashboard -----------------------------------------------------------
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "5000"))
    DEBUG: bool = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")

    # -- Agent priority order (highest first) --------------------------------
    AGENT_PRIORITY: list[str] = [
        "patient_intake",
        "medication_adherence",
        "follow_up",
        "appointment",
        "risk_prediction",
        "family_care",
        "voice_care",
        "pharmacy",
        "lab",
        "insurance",
    ]

    # -- Communication -------------------------------------------------------
    SMTP_HOST: str = os.getenv("SMTP_HOST", "localhost")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@healthcare-orchestra.local")

    # -- Risk thresholds ----------------------------------------------------
    RISK_THRESHOLDS: dict[str, int] = {
        "medication_missed_weight": 3,
        "followup_overdue_weight": 4,
        "lab_abnormal_weight": 5,
    }

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


config = _Config()
