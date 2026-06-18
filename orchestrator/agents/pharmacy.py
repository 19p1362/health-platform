"""
Healthcare Orchestra — Pharmacy Agent.

Queries medications approaching their refill threshold,
creates pharmacy_interactions entries for refill requests,
and sends notifications to patients.
"""

from __future__ import annotations

import logging

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.pharmacy")


def run(db: Database) -> dict:
    """Run the pharmacy agent.

    Args:
        db: Database instance.

    Returns:
        dict with results.
    """
    result: dict = {
        "medications_approaching_refill": 0,
        "refill_notifications_sent": 0,
        "pharmacy_interactions_created": 0,
        "errors": 0,
    }

    try:
        meds = db.get_medications_approaching_refill()
    except Exception as exc:
        logger.error("Failed to get medications approaching refill: %s", exc)
        result["errors"] += 1
        return result

    if not meds:
        logger.info("No medications approaching refill")
        return result

    for med in meds:
        med_id = med.get("id", "")
        patient_id = med.get("patient_id", "")
        med_name = med.get("name", "Unknown")
        dosage = med.get("dosage", "")
        frequency = med.get("frequency", "")
        refill_count = med.get("refill_count", 0)
        first_name = med.get("first_name", "") or ""
        last_name = med.get("last_name", "") or ""
        phone = med.get("phone", "") or ""

        if not med_id or not patient_id:
            continue

        result["medications_approaching_refill"] += 1

        try:
            # Create pharmacy interaction record
            interaction_details = (
                f"Refill needed for {med_name} ({dosage}, {frequency}). "
                f"Current refill count: {refill_count}"
            )

            pi_id = db.create_pharmacy_interaction(
                patient_id=patient_id,
                medication_id=med_id,
                interaction_type="refill_request",
                details=interaction_details,
            )
            result["pharmacy_interactions_created"] += 1

            # Send notification
            notification_msg = (
                f"🔄 *Refill Reminder*\n\n"
                f"Hi {first_name}, your medication *{med_name}* "
                f"({dosage}, {frequency}) is approaching its refill date.\n\n"
                f"Current refills remaining: {refill_count}\n\n"
                f"Please contact your pharmacy to arrange a refill, "
                f"or reply *refill* to request one here.\n\n"
                f"Stay healthy! 💊"
            )

            if phone:
                try:
                    db.log_communication(
                        channel="internal",
                        recipient=phone,
                        subject=f"Refill Reminder: {med_name}",
                        body=notification_msg,
                    )
                    result["refill_notifications_sent"] += 1
                except Exception as comm_exc:
                    logger.warning(
                        "Pharmacy notification failed for %s: %s",
                        phone, comm_exc,
                    )
                    db.log_communication(
                        channel="internal",
                        recipient=phone,
                        subject=f"Refill Reminder: {med_name}",
                        body=notification_msg,
                        status="failed",
                    )

            db.log_agent_action(
                agent_name="pharmacy",
                action="refill_reminder_sent",
                patient_id=patient_id,
                details=(
                    f"Medication: {med_name}, "
                    f"refills remaining: {refill_count}, "
                    f"interaction_id: {pi_id}"
                ),
            )

        except Exception as exc:
            logger.error(
                "Error processing refill for medication %s: %s",
                med_id, exc,
            )
            db.log_agent_action(
                agent_name="pharmacy",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Pharmacy agent complete: %d approaching refill, "
        "%d interactions created, %d notifications sent, %d errors",
        result["medications_approaching_refill"],
        result["pharmacy_interactions_created"],
        result["refill_notifications_sent"],
        result["errors"],
    )
    return result
