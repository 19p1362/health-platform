"""
Healthcare Orchestra — Family Care Agent.

Runs weekly to generate a summary of each patient's recent activity:
medications, lab results, appointments, and follow-ups.

The summary is stored for family/caregiver access.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.family_care")


def run(db: Database) -> dict:
    """Run the family care agent.

    Args:
        db: Database instance.

    Returns:
        dict with results.
    """
    result: dict = {
        "summaries_generated": 0,
        "patients_processed": 0,
        "errors": 0,
    }

    try:
        patients = db.get_patients()
    except Exception as exc:
        logger.error("Failed to get patients: %s", exc)
        result["errors"] += 1
        return result

    today = datetime.utcnow()
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    for patient in patients:
        patient_id = patient.get("id", "")
        first_name = patient.get("first_name", "") or ""
        last_name = patient.get("last_name", "") or ""

        if not patient_id:
            continue

        result["patients_processed"] += 1

        try:
            sections: list[str] = []

            # Header
            sections.append(
                f"🏥 *Weekly Care Summary*\n"
                f"Patient: {first_name} {last_name}\n"
                f"Period: {week_ago} to {today_str}\n"
                f"{'─' * 40}"
            )

            # Medications section
            try:
                meds = db.get_medications(patient_id=patient_id)
                if meds:
                    sections.append("\n💊 *Medications*")
                    for m in meds:
                        name = m.get("name", "Unknown")
                        dosage = m.get("dosage", "")
                        freq = m.get("frequency", "")
                        sections.append(
                            f"  • {name} — {dosage} {freq}"
                        )

                    # Adherence
                    rate = db.get_adherence_rate(patient_id, days_back=7)
                    sections.append(
                        f"  Adherence rate: {rate:.0%}"
                    )
                else:
                    sections.append("\n💊 *Medications* — None active")
            except Exception as exc:
                logger.warning(
                    "Could not get medications for %s: %s",
                    patient_id, exc,
                )
                sections.append("\n💊 *Medications* — Data unavailable")

            # Lab results section
            try:
                labs = db.get_lab_orders(patient_id=patient_id)
                recent_labs = [
                    l for l in labs
                    if l.get("ordered_date", "") >= week_ago
                ]
                if recent_labs:
                    sections.append("\n🔬 *Recent Lab Results*")
                    for lab in recent_labs:
                        name = lab.get("test_name", "Test")
                        value = lab.get("result_value", "")
                        unit = lab.get("result_unit", "")
                        abnormal = lab.get("is_abnormal", 0)
                        flag = " ⚠️" if abnormal else ""
                        sections.append(
                            f"  • {name}: {value} {unit}{flag}"
                        )
                else:
                    sections.append(
                        "\n🔬 *Lab Results* — No recent results"
                    )
            except Exception as exc:
                logger.warning(
                    "Could not get labs for %s: %s", patient_id, exc,
                )
                sections.append("\n🔬 *Lab Results* — Data unavailable")

            # Appointments section
            try:
                appts = db.get_appointments(patient_id=patient_id)
                upcoming = [
                    a for a in appts
                    if a.get("scheduled_date", "") >= today_str
                ]
                if upcoming:
                    sections.append("\n📅 *Upcoming Appointments*")
                    for a in upcoming:
                        sections.append(
                            f"  • {a.get('appointment_type','Visit')} "
                            f"with {a.get('provider_name','Dr.')} "
                            f"on {a.get('scheduled_date','')} "
                            f"at {a.get('scheduled_time','')}"
                        )
                else:
                    sections.append(
                        "\n📅 *Appointments* — None upcoming"
                    )
            except Exception as exc:
                logger.warning(
                    "Could not get appointments for %s: %s",
                    patient_id, exc,
                )
                sections.append(
                    "\n📅 *Appointments* — Data unavailable"
                )

            # Follow-ups section
            try:
                fups = db.get_follow_ups(status="pending")
                patient_fups = [
                    f for f in fups
                    if f.get("patient_id") == patient_id
                ]
                if patient_fups:
                    sections.append("\n📋 *Pending Follow-Ups*")
                    for f in patient_fups:
                        due = f.get("due_date", "") or ""
                        overdue = ""
                        if due and due[:10] < today_str:
                            overdue = " ⏰ OVERDUE"
                        sections.append(
                            f"  • {f.get('description','Task')} "
                            f"(due: {due[:10] if due else 'N/A'}){overdue}"
                        )
            except Exception as exc:
                logger.warning(
                    "Could not get follow-ups for %s: %s",
                    patient_id, exc,
                )

            # Build summary text
            summary_text = "\n".join(sections)

            # Store the summary
            db.create_family_summary(
                patient_id=patient_id,
                summary_text=summary_text,
                summary_type="weekly",
            )

            result["summaries_generated"] += 1

            db.log_agent_action(
                agent_name="family_care",
                action="weekly_summary_generated",
                patient_id=patient_id,
                details=f"Summary generated for period {week_ago} to {today_str}",
            )

        except Exception as exc:
            logger.error(
                "Error generating family summary for %s: %s",
                patient_id, exc,
            )
            db.log_agent_action(
                agent_name="family_care",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Family care agent complete: %d patients processed, "
        "%d summaries generated, %d errors",
        result["patients_processed"],
        result["summaries_generated"],
        result["errors"],
    )
    return result
