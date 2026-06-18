"""
Healthcare Orchestra — Appointment Reminder Agent.

For patients with appointments scheduled today or tomorrow,
sends a reminder via WhatsApp and marks the appointment as notified.
"""

from __future__ import annotations

import logging

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.appointment")


def run(db: Database) -> dict:
    """Run the appointment reminder agent.

    Args:
        db: Database instance.

    Returns:
        dict with results breakdown.
    """
    result: dict = {
        "appointments_found": 0,
        "reminders_sent": 0,
        "already_notified": 0,
        "errors": 0,
    }

    try:
        appointments = db.get_appointments_today_tomorrow()
    except Exception as exc:
        logger.error("Failed to get upcoming appointments: %s", exc)
        result["errors"] += 1
        return result

    if not appointments:
        logger.info("No appointments for today or tomorrow")
        return result

    for apt in appointments:
        apt_id = apt.get("id", "")
        patient_id = apt.get("patient_id", "")
        first_name = apt.get("first_name", "") or ""
        last_name = apt.get("last_name", "") or ""
        phone = apt.get("phone", "") or ""
        provider = apt.get("provider_name", "") or "your provider"
        apt_type = apt.get("appointment_type", "") or "appointment"
        sched_date = apt.get("scheduled_date", "") or ""
        sched_time = apt.get("scheduled_time", "") or ""

        if not apt_id:
            continue

        result["appointments_found"] += 1

        try:
            # Check if already notified
            if apt.get("notified", 0) == 1:
                result["already_notified"] += 1
                continue

            # Determine if today or tomorrow
            from datetime import datetime
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            if sched_date == today_str:
                day_label = "today"
            else:
                day_label = "tomorrow"

            time_info = f" at {sched_time}" if sched_time else ""
            reminder_msg = (
                f"📅 *Appointment Reminder*\n\n"
                f"Hi {first_name}, this is a reminder that you have "
                f"a *{apt_type}* with {provider} "
                f"*{day_label}*{time_info}.\n\n"
                f"📍 Please arrive 15 minutes early.\n"
                f"📋 Bring your ID and insurance card.\n\n"
                f"Reply *help* for other options, or "
                f"send a photo of any documents you'd like us to review."
            )

            if phone:
                try:
                    db.log_communication(
                        channel="internal",
                        recipient=phone,
                        subject=f"Appointment Reminder ({day_label})",
                        body=reminder_msg,
                    )
                except Exception as comm_exc:
                    logger.warning(
                        "Communication failed for %s: %s", phone, comm_exc,
                    )
                    # Still log the communication
                    db.log_communication(
                        channel="internal",
                        recipient=phone,
                        subject=f"Appointment Reminder ({day_label})",
                        body=reminder_msg,
                        status="failed",
                    )

            # Mark as notified regardless of WhatsApp success
            db.mark_appointment_notified(apt_id)
            result["reminders_sent"] += 1

            db.log_agent_action(
                agent_name="appointment",
                action="reminder_sent",
                patient_id=patient_id,
                details=(
                    f"{apt_type} with {provider} on {sched_date} "
                    f"at {sched_time} — {day_label}"
                ),
            )

        except Exception as exc:
            logger.error(
                "Error processing appointment %s: %s", apt_id, exc
            )
            db.log_agent_action(
                agent_name="appointment",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Appointment reminders: %d found (%d already notified), "
        "%d sent, %d errors",
        result["appointments_found"],
        result["already_notified"],
        result["reminders_sent"],
        result["errors"],
    )
    return result
