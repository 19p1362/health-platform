"""
Healthcare Orchestra — Patient Intake Agent.

Finds patients in HealthBridge with incomplete data (missing phone, missing address)
and sends a WhatsApp welcome message via the communication layer.
"""

from __future__ import annotations

import logging

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.patient_intake")


def run(db: Database) -> dict:
    """Run the patient intake agent.

    Args:
        db: Database instance with patient data.

    Returns:
        dict with keys: patients_contacted, patients_skipped, errors
    """
    result: dict = {
        "patients_contacted": 0,
        "patients_skipped": 0,
        "errors": 0,
    }

    try:
        patients = db.get_patients_with_incomplete_data()
    except Exception as exc:
        logger.error("Failed to get patients with incomplete data: %s", exc)
        result["errors"] += 1
        return result

    if not patients:
        logger.info("No patients with incomplete data found")
        return result

    for patient in patients:
        patient_id = patient.get("id", "")
        phone = patient.get("phone", "") or ""
        first_name = patient.get("first_name", "") or ""
        last_name = patient.get("last_name", "") or ""
        address = patient.get("address", "") or ""

        missing_fields = []
        if not phone:
            missing_fields.append("phone number")
        if not address:
            missing_fields.append("address")

        try:
            welcome_msg = (
                f"👋 Welcome to HealthBridge, {first_name} {last_name}!\n\n"
                "We're excited to help you manage your healthcare. "
                "To get started, please provide your:\n"
            )
            if missing_fields:
                welcome_msg += f"📝 Missing: {', '.join(missing_fields)}\n\n"
            welcome_msg += (
                "Reply with:\n"
                "• *status* — Check your care status\n"
                "• *medicines* — View medications\n"
                "• *appointments* — Upcoming appointments\n"
                "• Send a photo of your prescription or lab report"
            )

            if phone:
                # Try to send WhatsApp via the webhook infrastructure
                try:
                    form_data = {
                        "From": f"whatsapp:{phone}",
                        "To": "system",
                        "Body": "welcome",
                    }
                    handle_webhook(form_data)
                    db.log_communication(
                        channel="whatsapp",
                        recipient=phone,
                        subject="Welcome",
                        body=welcome_msg,
                    )
                    result["patients_contacted"] += 1
                except Exception as comm_exc:
                    logger.warning(
                        "WhatsApp send failed for %s: %s — logging only",
                        phone, comm_exc,
                    )
                    db.log_communication(
                        channel="whatsapp",
                        recipient=phone,
                        subject="Welcome (logged)",
                        body=welcome_msg,
                        status="failed",
                    )
                    result["errors"] += 1
            else:
                logger.info(
                    "Patient %s has no phone — skipping WhatsApp welcome",
                    patient_id,
                )
                result["patients_skipped"] += 1

            db.log_agent_action(
                agent_name="patient_intake",
                action="welcome_message",
                patient_id=patient_id,
                details=f"Missing: {', '.join(missing_fields)}. Contacted: {bool(phone)}",
            )

        except Exception as exc:
            logger.error("Error processing patient %s: %s", patient_id, exc)
            db.log_agent_action(
                agent_name="patient_intake",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Patient intake complete: %d contacted, %d skipped, %d errors",
        result["patients_contacted"],
        result["patients_skipped"],
        result["errors"],
    )
    return result
