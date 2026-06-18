"""
Healthcare Orchestra — Agent Registry.

Exports all agent run functions for discovery by the orchestrator.
"""

from __future__ import annotations

from .patient_intake import run as run_patient_intake
from .medication_adherence import run as run_medication_adherence
from .follow_up import run as run_follow_up
from .appointment import run as run_appointment
from .risk_prediction import run as run_risk_prediction
from .family_care import run as run_family_care
from .voice_care import run as run_voice_care
from .pharmacy import run as run_pharmacy
from .lab import run as run_lab
from .insurance import run as run_insurance

__all__ = [
    "run_patient_intake",
    "run_medication_adherence",
    "run_follow_up",
    "run_appointment",
    "run_risk_prediction",
    "run_family_care",
    "run_voice_care",
    "run_pharmacy",
    "run_lab",
    "run_insurance",
]

# Agent metadata — used by the orchestrator for priority ordering and logging
AGENT_META: dict[str, dict] = {
    "patient_intake": {
        "name": "patient_intake",
        "function": run_patient_intake,
        "description": "Onboard new patients, fill missing data, send welcome messages",
    },
    "medication_adherence": {
        "name": "medication_adherence",
        "function": run_medication_adherence,
        "description": "Track medication adherence and send reminders for missed doses",
    },
    "follow_up": {
        "name": "follow_up",
        "function": run_follow_up,
        "description": "Manage overdue follow-ups with escalation",
    },
    "appointment": {
        "name": "appointment",
        "function": run_appointment,
        "description": "Send appointment reminders for today/tomorrow",
    },
    "risk_prediction": {
        "name": "risk_prediction",
        "function": run_risk_prediction,
        "description": "Score patients on risk factors (medications, labs, follow-ups)",
    },
    "family_care": {
        "name": "family_care",
        "function": run_family_care,
        "description": "Generate weekly family care summaries",
    },
    "voice_care": {
        "name": "voice_care",
        "function": run_voice_care,
        "description": "Identify patients eligible for voice call outreach",
    },
    "pharmacy": {
        "name": "pharmacy",
        "function": run_pharmacy,
        "description": "Handle medication refill requests and pharmacy interactions",
    },
    "lab": {
        "name": "lab",
        "function": run_lab,
        "description": "Process lab results and notify patients of abnormal values",
    },
    "insurance": {
        "name": "insurance",
        "function": run_insurance,
        "description": "Track stalled insurance claims and flag for attention",
    },
}
