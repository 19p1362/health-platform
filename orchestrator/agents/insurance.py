"""
Healthcare Orchestra — Insurance Agent.

Queries the insurance_claims table for stalled claims (claims that
are stuck in non-terminal statuses), flags them for attention,
and logs for the care coordinator.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.agent.insurance")


def run(db: Database) -> dict:
    """Run the insurance agent.

    Args:
        db: Database instance.

    Returns:
        dict with results.
    """
    result: dict = {
        "claims_checked": 0,
        "stalled_claims_found": 0,
        "claims_flagged": 0,
        "errors": 0,
    }

    try:
        stalled_claims = db.get_insurance_claims(stalled_only=True)
    except Exception as exc:
        logger.error("Failed to get insurance claims: %s", exc)
        result["errors"] += 1
        return result

    if not stalled_claims:
        logger.info("No stalled insurance claims found")
        db.log_agent_action(
            agent_name="insurance",
            action="checked",
            details="No stalled claims found",
        )
        return result

    result["stalled_claims_found"] = len(stalled_claims)

    today = datetime.utcnow()

    for claim in stalled_claims:
        claim_id = claim.get("id", "")
        patient_id = claim.get("patient_id", "")
        first_name = claim.get("first_name", "") or ""
        last_name = claim.get("last_name", "") or ""
        claim_number = claim.get("claim_number", "") or "N/A"
        payer_name = claim.get("payer_name", "") or "Unknown"
        amount = claim.get("amount", 0) or 0
        status = claim.get("status", "submitted") or "submitted"
        submitted_date = claim.get("submitted_date", "") or ""

        if not claim_id:
            continue

        try:
            # Calculate days since submission
            days_stalled = 0
            if submitted_date:
                try:
                    sub_date = datetime.strptime(
                        submitted_date[:10], "%Y-%m-%d"
                    )
                    days_stalled = (today - sub_date).days
                except (ValueError, TypeError):
                    pass

            # Determine stall reason
            if days_stalled >= 60:
                stall_reason = (
                    "Claim has been pending for over 60 days — "
                    "escalation recommended"
                )
                priority = "HIGH"
            elif days_stalled >= 30:
                stall_reason = (
                    "Claim pending for over 30 days — needs follow-up"
                )
                priority = "MEDIUM"
            elif days_stalled >= 14:
                stall_reason = (
                    "Claim pending for 2+ weeks — routine check"
                )
                priority = "LOW"
            else:
                stall_reason = f"Claim is in '{status}' status"
                priority = "INFO"

            # Update the claim with stall reason
            try:
                db._get_conn().execute(
                    "UPDATE insurance_claims SET stalled_reason=? WHERE id=?",
                    (stall_reason, claim_id),
                )
                db._get_conn().commit()
            except Exception:
                pass

            # Flag the claim
            db.flag_insurance_claim(claim_id)
            result["claims_flagged"] += 1

            notification_msg = (
                f"🏥 *Insurance Claim Alert*\n\n"
                f"Claim #{claim_number}\n"
                f"Patient: {first_name} {last_name}\n"
                f"Payer: {payer_name}\n"
                f"Amount: ${amount:.2f}\n"
                f"Status: {status}\n"
                f"Submitted: {submitted_date[:10] if submitted_date else 'N/A'}\n"
                f"Days Pending: {days_stalled}\n"
                f"Priority: {priority}\n\n"
                f"{stall_reason}\n\n"
                f"Please review this claim and take appropriate action."
            )

            # Log communication for care coordinator
            db.log_communication(
                channel="internal",
                recipient="care_coordinator",
                subject=(
                    f"[{priority}] Stalled Claim #{claim_number} — "
                    f"{first_name} {last_name}"
                ),
                body=notification_msg,
            )

            db.log_agent_action(
                agent_name="insurance",
                action="claim_flagged",
                patient_id=patient_id,
                details=(
                    f"Claim #{claim_number}, payer={payer_name}, "
                    f"amount=${amount:.2f}, stalled={days_stalled}d, "
                    f"priority={priority}, reason: {stall_reason}"
                ),
            )

            logger.info(
                "Flagged claim #%s for %s %s: %s (%d days stalled)",
                claim_number, first_name, last_name,
                priority, days_stalled,
            )

        except Exception as exc:
            logger.error(
                "Error processing claim %s: %s", claim_id, exc
            )
            db.log_agent_action(
                agent_name="insurance",
                action="error",
                patient_id=patient_id,
                details=str(exc),
                status="error",
            )
            result["errors"] += 1

    logger.info(
        "Insurance agent complete: %d claims checked, "
        "%d stalled, %d flagged, %d errors",
        result["claims_checked"],
        result["stalled_claims_found"],
        result["claims_flagged"],
        result["errors"],
    )
    return result
