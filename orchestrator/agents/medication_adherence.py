"""
Healthcare Orchestra — Medication Adherence Agent.

Queries the database for medication data, checks adherence logs for missed doses,
and sends reminders via WhatsApp for doses that were not taken.
Tracks adherence rate per patient.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.medication_adherence")


def run(db: Database) -> dict:
    """Run the medication adherence agent.

    Args:
        db: Database instance.

    Returns:
        dict with keys: patients_checked, reminders_sent, missed_doses_found, errors
    """
    result: dict = {
        "patients_checked": 0,
        "reminders_sent": 0,
        "missed_doses_found": 0,
        "errors": 0,
    }

    try:
        patients = db.get_patients()
    except Exception as exc:
        logger.error("Failed to get patients: %s", exc)
        result["errors"] += 1
        return result

    today = datetime.utcnow().strftime("%Y-%m-%d")

    for patient in patients:
        patient_id = patient.get("id", "")
        phone = patient.get("phone", "") or ""
        first_name = patient.get("first_name", "") or ""

        if not patient_id:
            continue

        result["patients_checked"] += 1

        try:
            # Get adherence rate
            adherence_rate = db.get_adherence_rate(patient_id, days_back=7)
            missed_doses = db.get_missed_doses(patient_id, days_back=7)

            if not missed_doses:
                logger.debug(
                    "Patient %s: 100%% adherence this week", patient_id
                )
                continue

            result["missed_doses_found"] += len(missed_doses)

            # Group missed doses by medication
            meds_missed: dict[str, list] = {}
            for dose in missed_doses:
                med_name = dose.get("medication_name", "Unknown medication")
                if med_name not in meds_missed:
                    meds_missed[med_name] = []
                meds_missed[med_name].append(dose)

            med_lines = []
            for med_name, doses in meds_missed.items():
                dates = [
                    d.get("scheduled_date", "unknown")[:10] for d in doses
                ]
                med_lines.append(f"💊 *{med_name}* — missed on: {', '.join(dates)}")

            reminder_body = (
                f"⏰ *Medication Reminder* — {first_name}\n\n"
                f"You missed some doses this week:\n"
                + "\n".join(med_lines) +
                f"\n\nYour current adherence rate: {adherence_rate:.0%}\n\n"
                f"Please take your medications as prescribed. "
                f"Reply *medicines* for your full schedule, "
                f"or *help* for options."
            )

            if phone:
                try:
                    db.log_communication(
                        channel="internal",
                        recipient=phone,
                        subject="Medication Reminder",
                        body=reminder_body,
                    )
                    result["reminders_sent"] += 1
                except Exception as comm_exc:
                    logger.warning(
                        "Reminder failed for %s: %s",
                        phone, comm_exc,
                    )
                    result["errors"] += 1
            else:
                logger.info(
                    "Patient %s has no phone — logging adherence warning",
                    patient_id,
                )

            db.log_agent_action(
                agent_name="medication_adherence",
                action="reminder_sent",
                patient_id=patient_id,
                details=(
                    f"Missed {len(missed_doses)} doses, "
                    f"rate={adherence_rate:.0%}, "
                    f"meds={list(meds_missed.keys())}"
                ),
            )

        except Exception as exc:
            logger.error(
                "Error checking adherence for patient %s: %s",
                patient_id, exc,
            )
            db.log_agent_action(
                agent_name="medication_adherence",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Medication adherence complete: %d patients checked, "
        "%d missed doses, %d reminders sent, %d errors",
        result["patients_checked"],
        result["missed_doses_found"],
        result["reminders_sent"],
        result["errors"],
    )
    return result
