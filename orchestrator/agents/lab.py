"""
Healthcare Orchestra — Lab Results Agent.

Queries the database for recent lab results, checks for abnormal values,
and notifies patients of abnormal results with appropriate guidance.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.lab")


def run(db: Database) -> dict:
    """Run the lab results agent.

    Args:
        db: Database instance.

    Returns:
        dict with results.
    """
    result: dict = {
        "labs_checked": 0,
        "abnormal_found": 0,
        "patients_notified": 0,
        "errors": 0,
    }

    try:
        all_labs = db.get_lab_orders()
    except Exception as exc:
        logger.error("Failed to get lab orders: %s", exc)
        result["errors"] += 1
        return result

    if not all_labs:
        logger.info("No lab orders found")
        return result

    result["labs_checked"] = len(all_labs)

    # Get only abnormal lab results
    abnormal_labs = [
        lab for lab in all_labs if lab.get("is_abnormal", 0) == 1
    ]

    if not abnormal_labs:
        logger.info("No abnormal lab results found")
        db.log_agent_action(
            agent_name="lab",
            action="checked",
            details=f"Checked {len(all_labs)} lab results, none abnormal",
        )
        return result

    result["abnormal_found"] = len(abnormal_labs)

    # Group abnormal labs by patient
    from collections import defaultdict
    by_patient: dict[str, list[dict]] = defaultdict(list)
    for lab in abnormal_labs:
        pid = lab.get("patient_id", "")
        if pid:
            by_patient[pid].append(lab)

    for patient_id, labs in by_patient.items():
        try:
            patient = db.get_patient(patient_id)
            if not patient:
                continue

            first_name = patient.get("first_name", "") or ""
            last_name = patient.get("last_name", "") or ""
            phone = patient.get("phone", "") or ""

            # Build notification
            lab_lines = []
            for lab in labs:
                name = lab.get("test_name", "Test")
                value = lab.get("result_value", "")
                unit = lab.get("result_unit", "")
                ref_range = lab.get("reference_range", "")
                ordered = lab.get("ordered_date", "") or ""
                lab_lines.append(
                    f"  • {name}: *{value} {unit}* "
                    f"(ref: {ref_range}) "
                    f"[{ordered[:10]}]"
                )

            notification_msg = (
                f"🔬 *Lab Result Alert*\n\n"
                f"Hi {first_name}, some of your recent lab results "
                f"show values outside the normal range.\n\n"
                + "\n".join(lab_lines) +
                f"\n\n⚠️ *Please review these results with your doctor.*\n\n"
                f"Reply *lab* to see all your results, or "
                f"send a photo of any new lab reports."
            )

            # Notify via WhatsApp
            if phone:
                try:
                    db.log_communication(
                        channel="internal",
                        recipient=phone,
                        subject="Abnormal Lab Results Alert",
                        body=notification_msg,
                    )
                    result["patients_notified"] += 1
                except Exception as comm_exc:
                    logger.warning(
                        "Lab notification failed for %s: %s",
                        phone, comm_exc,
                    )
                    db.log_communication(
                        channel="internal",
                        recipient=phone,
                        subject="Abnormal Lab Results Alert",
                        body=notification_msg,
                        status="failed",
                    )

            db.log_agent_action(
                agent_name="lab",
                action="abnormal_result_notified",
                patient_id=patient_id,
                details=(
                    f"{len(labs)} abnormal result(s): "
                    + "; ".join(
                        f"{l.get('test_name','')}={l.get('result_value','')}"
                        for l in labs
                    )
                ),
            )

        except Exception as exc:
            logger.error(
                "Error notifying patient %s about lab results: %s",
                patient_id, exc,
            )
            db.log_agent_action(
                agent_name="lab",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Lab agent complete: %d labs checked, %d abnormal, "
        "%d patients notified, %d errors",
        result["labs_checked"],
        result["abnormal_found"],
        result["patients_notified"],
        result["errors"],
    )
    return result
