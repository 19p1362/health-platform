"""
Healthcare Orchestra — Risk Prediction Agent.

Scores patients on key risk factors:
- Missed medications (adherence rate < 80%)
- Overdue follow-ups (pending beyond due date)
- Abnormal lab values

Returns a risk score (LOW / MEDIUM / HIGH / CRITICAL) and logs
high-risk patients for care coordinator attention.
"""

from __future__ import annotations

import logging
from datetime import datetime

from db_adapter import Database
from config import config

logger = logging.getLogger("healthcare_orchestra.agent.risk_prediction")


def _compute_risk_score(
    missed_meds: int,
    overdue_fups: int,
    abnormal_labs: int,
) -> tuple[str, int]:
    """Compute risk level and numeric score."""
    weights = config.RISK_THRESHOLDS
    score = (
        missed_meds * weights.get("medication_missed_weight", 3)
        + overdue_fups * weights.get("followup_overdue_weight", 4)
        + abnormal_labs * weights.get("lab_abnormal_weight", 5)
    )

    if score >= 20:
        return "CRITICAL", score
    elif score >= 12:
        return "HIGH", score
    elif score >= 5:
        return "MEDIUM", score
    else:
        return "LOW", score


def run(db: Database) -> dict:
    """Run the risk prediction agent.

    Args:
        db: Database instance.

    Returns:
        dict with results.
    """
    result: dict = {
        "patients_scored": 0,
        "low_risk": 0,
        "medium_risk": 0,
        "high_risk": 0,
        "critical_risk": 0,
        "errors": 0,
    }

    try:
        patients = db.get_patients()
    except Exception as exc:
        logger.error("Failed to get patients: %s", exc)
        result["errors"] += 1
        return result

    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    for patient in patients:
        patient_id = patient.get("id", "")
        if not patient_id:
            continue

        try:
            # --- Factor 1: Missed medications ---
            missed_doses = db.get_missed_doses(patient_id, days_back=14)
            missed_meds_count = len(missed_doses)

            # Also factor in adherence rate
            adherence_rate = db.get_adherence_rate(patient_id, days_back=14)
            if adherence_rate < 0.8 and missed_meds_count == 0:
                # If low adherence but no recent missed records,
                # still count as at least 1 missed signal
                missed_meds_count = 1

            # --- Factor 2: Overdue follow-ups ---
            overdue_fups = 0
            try:
                all_fups = db.get_follow_ups(status="pending")
                for fup in all_fups:
                    if fup.get("patient_id") != patient_id:
                        continue
                    due = fup.get("due_date", "")
                    if due and due[:10] < today_str:
                        overdue_fups += 1
            except Exception:
                pass

            # --- Factor 3: Abnormal lab values ---
            abnormal_labs = len(
                db.get_lab_orders(patient_id=patient_id, abnormal_only=True)
            )

            # --- Compute risk ---
            risk_label, risk_score = _compute_risk_score(
                missed_meds=missed_meds_count,
                overdue_fups=overdue_fups,
                abnormal_labs=abnormal_labs,
            )

            # --- Update patient record ---
            try:
                db._get_conn().execute(
                    "UPDATE patients SET risk_score=? WHERE id=?",
                    (risk_label, patient_id),
                )
                db._get_conn().commit()
            except Exception:
                pass

            result["patients_scored"] += 1
            if risk_label == "LOW":
                result["low_risk"] += 1
            elif risk_label == "MEDIUM":
                result["medium_risk"] += 1
            elif risk_label == "HIGH":
                result["high_risk"] += 1
            elif risk_label == "CRITICAL":
                result["critical_risk"] += 1

            details = (
                f"score={risk_score}, level={risk_label}, "
                f"missed_meds={missed_meds_count}, "
                f"overdue_fups={overdue_fups}, "
                f"abnormal_labs={abnormal_labs}"
            )

            db.log_agent_action(
                agent_name="risk_prediction",
                action="risk_scored",
                patient_id=patient_id,
                details=details,
            )

            # Flag critical patients for care coordinator
            if risk_label in ("HIGH", "CRITICAL"):
                logger.warning(
                    "HIGH/CRITICAL patient %s %s: %s",
                    patient.get("first_name", ""),
                    patient.get("last_name", ""),
                    details,
                )

        except Exception as exc:
            logger.error(
                "Error scoring risk for patient %s: %s",
                patient_id, exc,
            )
            db.log_agent_action(
                agent_name="risk_prediction",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Risk prediction complete: %d scored "
        "(LOW=%d, MEDIUM=%d, HIGH=%d, CRITICAL=%d), %d errors",
        result["patients_scored"],
        result["low_risk"],
        result["medium_risk"],
        result["high_risk"],
        result["critical_risk"],
        result["errors"],
    )
    return result
