"""
Healthcare Orchestra — Follow-Up Agent.

Checks follow_ups table for overdue items and escalates
based on how many days overdue they are:
- 1 day: gentle reminder
- 3 days: urgent reminder
- 7+ days: critical escalation

Creates communication_log entries for each escalation.
"""

from __future__ import annotations

import logging
from datetime import datetime

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.follow_up")


def _compute_overdue_days(due_date_str: str) -> int:
    """Compute how many days past due a follow-up is."""
    if not due_date_str:
        return 0
    try:
        due = datetime.strptime(due_date_str[:10], "%Y-%m-%d")
        today = datetime.utcnow()
        delta = (today - due).days
        return max(0, delta)
    except (ValueError, TypeError):
        return 0


def run(db: Database) -> dict:
    """Run the follow-up agent.

    Args:
        db: Database instance.

    Returns:
        dict with results breakdown.
    """
    result: dict = {
        "overdue_found": 0,
        "reminders_sent": 0,
        "urgent_sent": 0,
        "critical_sent": 0,
        "errors": 0,
    }

    try:
        follow_ups = db.get_follow_ups(status="pending")
    except Exception as exc:
        logger.error("Failed to get pending follow-ups: %s", exc)
        result["errors"] += 1
        return result

    if not follow_ups:
        logger.info("No pending follow-ups found")
        return result

    for fup in follow_ups:
        fup_id = fup.get("id", "")
        patient_id = fup.get("patient_id", "")
        due_date = fup.get("due_date", "") or ""
        first_name = fup.get("first_name", "") or ""
        last_name = fup.get("last_name", "") or ""
        phone = fup.get("phone", "") or ""
        description = fup.get("description", "") or ""
        follow_up_type = fup.get("follow_up_type", "") or ""

        if not fup_id or not patient_id:
            continue

        try:
            overdue_days = _compute_overdue_days(due_date)

            if overdue_days <= 0:
                continue

            result["overdue_found"] += 1

            # Determine escalation level
            if overdue_days >= 7:
                level = "critical"
                severity = "🔴 CRITICAL"
                action_text = (
                    f"This follow-up is {overdue_days} days overdue and "
                    "requires immediate attention."
                )
                result["critical_sent"] += 1
            elif overdue_days >= 3:
                level = "urgent"
                severity = "🟠 URGENT"
                action_text = (
                    f"This follow-up is {overdue_days} days overdue. "
                    "Please address as soon as possible."
                )
                result["urgent_sent"] += 1
            else:
                level = "reminder"
                severity = "🟡 Reminder"
                action_text = (
                    f"This follow-up is {overdue_days} day(s) overdue. "
                    "A gentle reminder to complete it."
                )
                result["reminders_sent"] += 1

            escalation_message = (
                f"{severity} — Follow-Up Needed\n\n"
                f"Patient: {first_name} {last_name}\n"
                f"Type: {follow_up_type}\n"
                f"Description: {description}\n"
                f"Due Date: {due_date[:10] if due_date else 'N/A'}\n"
                f"Overdue: {overdue_days} day(s)\n\n"
                f"{action_text}"
            )

            # Log the communication
            db.log_communication(
                channel="internal",
                recipient=phone or "care_coordinator",
                subject=f"Follow-Up {level.upper()}: {description[:50]}",
                body=escalation_message,
            )

            # Update follow-up record with escalation info
            try:
                db._get_conn().execute(
                    """UPDATE follow_ups SET days_overdue=?,
                       escalated=1, escalation_level=?
                       WHERE id=?""",
                    (overdue_days, level, fup_id),
                )
                db._get_conn().commit()
            except Exception:
                pass

            db.log_agent_action(
                agent_name="follow_up",
                action=f"escalation_{level}",
                patient_id=patient_id,
                details=(
                    f"Overdue {overdue_days}d: {description[:100]}, "
                    f"escalated to {level}"
                ),
            )

        except Exception as exc:
            logger.error(
                "Error processing follow-up %s: %s", fup_id, exc
            )
            db.log_agent_action(
                agent_name="follow_up",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Follow-up agent complete: %d overdue, "
        "%d reminders, %d urgent, %d critical, %d errors",
        result["overdue_found"],
        result["reminders_sent"],
        result["urgent_sent"],
        result["critical_sent"],
        result["errors"],
    )
    return result
