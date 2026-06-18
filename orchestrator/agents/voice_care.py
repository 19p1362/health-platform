"""
Healthcare Orchestra — Voice Care Agent.

Identifies patients who are eligible for voice call outreach:
- High or critical risk patients
- Patients who have not responded to WhatsApp messages
- Patients with a phone number but no WhatsApp activity

Logs voice call eligibility records for the care coordinator.
"""

from __future__ import annotations

import logging

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.voice_care")


def run(db: Database) -> dict:
    """Run the voice care agent.

    Args:
        db: Database instance.

    Returns:
        dict with results.
    """
    result: dict = {
        "eligible_patients": 0,
        "high_risk_eligible": 0,
        "no_whatsapp_response": 0,
        "errors": 0,
    }

    try:
        patients = db.get_patients()
    except Exception as exc:
        logger.error("Failed to get patients: %s", exc)
        result["errors"] += 1
        return result

    for patient in patients:
        patient_id = patient.get("id", "")
        phone = patient.get("phone", "") or ""
        risk_score = patient.get("risk_score", "LOW") or "LOW"

        if not patient_id:
            continue

        # Skip patients without a phone number
        if not phone:
            continue

        try:
            eligible = False
            reasons: list[str] = []

            # --- Criterion 1: High or critical risk ---
            if risk_score in ("HIGH", "CRITICAL"):
                eligible = True
                reasons.append(f"Risk score is {risk_score}")
                result["high_risk_eligible"] += 1

            # --- Criterion 2: No WhatsApp response ---
            try:
                recent_comms = db.get_recent_communications(
                    channel="whatsapp", limit=20
                )
                patient_comms = [
                    c for c in recent_comms
                    if c.get("recipient", "").strip() == phone.strip()
                ]
                failed_comms = [
                    c for c in patient_comms
                    if c.get("status") == "failed"
                ]
                if len(failed_comms) >= 3:
                    eligible = True
                    if "no WhatsApp response" not in reasons:
                        reasons.append(
                            f"{len(failed_comms)} failed WhatsApp messages"
                        )
                        result["no_whatsapp_response"] += 1
            except Exception:
                pass

            # --- Log eligibility ---
            if eligible:
                db.set_voice_call_eligibility(
                    patient_id=patient_id,
                    eligible=True,
                    reason="; ".join(reasons),
                )
                result["eligible_patients"] += 1
                logger.info(
                    "Patient %s eligible for voice call: %s",
                    patient_id, "; ".join(reasons),
                )

            db.log_agent_action(
                agent_name="voice_care",
                action="eligibility_check",
                patient_id=patient_id,
                details=(
                    f"Eligible={eligible}, risk={risk_score}, "
                    f"phone={'yes' if phone else 'no'}, "
                    f"reasons={'; '.join(reasons) if reasons else 'none'}"
                ),
            )

        except Exception as exc:
            logger.error(
                "Error checking voice eligibility for %s: %s",
                patient_id, exc,
            )
            db.log_agent_action(
                agent_name="voice_care",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Voice care agent complete: %d eligible "
        "(%d high-risk, %d no WhatsApp response), %d errors",
        result["eligible_patients"],
        result["high_risk_eligible"],
        result["no_whatsapp_response"],
        result["errors"],
    )
    return result
