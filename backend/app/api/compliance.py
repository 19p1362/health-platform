"""HealthBridge Platform — DPDP Compliance & Administration API Routes"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db, AsyncSession
from app.models import (
    DataBreach, BreachNotification, DataPrincipalRequest,
    ErasureSchedule, AuditLog, AuditAction, BreachStatus
)
from app.security.rbac import require_permission
from app.security.audit import log_action
from app.services.dpdp_compliance import DpdpComplianceService
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/compliance", tags=["DPDP Compliance"])
compliance = DpdpComplianceService()


# ── Schemas ──

class BreachReportRequest(BaseModel):
    description: str
    breach_type: str = "UNAUTHORIZED_ACCESS"
    severity: str = "MEDIUM"
    occurred_at: Optional[str] = None
    affected_patient_ids: list[str] = []
    affected_data_categories: list[str] = []
    remediation_steps: Optional[str] = None


# ── Breach Management (DPDP Section 8) ──

@router.get("/breaches")
async def list_breaches(
    status_filter: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """List all data breach events."""
    query = select(DataBreach).order_by(DataBreach.detected_at.desc())
    if status_filter:
        try:
            bs = BreachStatus(status_filter)
            query = query.where(DataBreach.status == bs)
        except ValueError:
            pass
    query = query.limit(limit)

    result = await db.execute(query)
    breaches = result.scalars().all()

    return [
        {
            "breach_id": b.breach_id,
            "description": b.description[:200] + "..." if len(b.description) > 200 else b.description,
            "breach_type": b.breach_type,
            "severity": b.severity.value if b.severity else None,
            "status": b.status.value if b.status else None,
            "detected_at": b.detected_at.isoformat(),
            "occurred_at": b.occurred_at.isoformat() if b.occurred_at else None,
            "affected_patient_count": b.affected_patient_count,
            "board_notified": b.board_notified,
            "users_notified": b.users_notified,
            "board_report_deadline": b.board_report_deadline.isoformat() if b.board_report_deadline else None,
        }
        for b in breaches
    ]


@router.get("/breaches/{breach_id}")
async def get_breach_detail(
    breach_id: str,
    current_user = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed breach information."""
    result = await db.execute(
        select(DataBreach).where(DataBreach.breach_id == breach_id)
    )
    breach = result.scalar_one_or_none()
    if not breach:
        raise HTTPException(status_code=404, detail="Breach not found")

    # Get notifications
    notif_result = await db.execute(
        select(BreachNotification).where(BreachNotification.breach_id == breach.id)
    )
    notifications = notif_result.scalars().all()

    return {
        "breach_id": breach.breach_id,
        "description": breach.description,
        "breach_type": breach.breach_type,
        "severity": breach.severity.value if breach.severity else None,
        "status": breach.status.value if breach.status else None,
        "detected_at": breach.detected_at.isoformat(),
        "occurred_at": breach.occurred_at.isoformat() if breach.occurred_at else None,
        "contained_at": breach.contained_at.isoformat() if breach.contained_at else None,
        "resolved_at": breach.resolved_at.isoformat() if breach.resolved_at else None,
        "affected_patient_count": breach.affected_patient_count,
        "affected_data_categories": breach.affected_data_categories,
        "remediation_steps": breach.remediation_steps,
        "root_cause": breach.root_cause,
        "board_notified": breach.board_notified,
        "board_notified_at": breach.board_notified_at.isoformat() if breach.board_notified_at else None,
        "board_report_submitted": breach.board_report_submitted,
        "board_report_deadline": breach.board_report_deadline.isoformat() if breach.board_report_deadline else None,
        "users_notified": breach.users_notified,
        "users_notified_at": breach.users_notified_at.isoformat() if breach.users_notified_at else None,
        "investigator_notes": breach.investigator_notes,
        "notifications": [
            {
                "channel": n.channel,
                "recipient": n.recipient,
                "sent_at": n.sent_at.isoformat(),
                "delivered": n.delivered,
            }
            for n in notifications
        ],
    }


@router.post("/breaches/report")
async def report_breach(
    request: BreachReportRequest,
    req: Request,
    current_user = Depends(require_permission("system.admin")),
    db: AsyncSession = Depends(get_db),
):
    """Report a personal data breach (DPDP Section 8)."""
    import uuid
    breach_id = f"HB-BRCH-{uuid.uuid4().hex[:8].upper()}"

    occurred_at = None
    if request.occurred_at:
        try:
            occurred_at = datetime.fromisoformat(request.occurred_at)
        except ValueError:
            pass

    breach = DataBreach(
        id=str(uuid.uuid4()),
        breach_id=breach_id,
        description=request.description,
        breach_type=request.breach_type,
        severity=request.severity,
        status=BreachStatus.DETECTED,
        detected_at=datetime.utcnow(),
        occurred_at=occurred_at or datetime.utcnow(),
        affected_patient_count=len(request.affected_patient_ids),
        affected_data_categories=request.affected_data_categories,
        remediation_steps=request.remediation_steps,
        board_report_deadline=datetime.utcnow() + timedelta(hours=72),
    )
    db.add(breach)

    # Create notifications for affected patients
    for patient_id in request.affected_patient_ids:
        notification = BreachNotification(
            breach_id=breach.id,
            patient_id=patient_id,
            channel="EMAIL",
            recipient=patient_id,
            breach_description=request.description,
            mitigation_measures=request.remediation_steps or "Investigation in progress",
        )
        db.add(notification)

    await db.flush()

    await log_action(
        action=AuditAction.BREACH_DETECTED,
        description=f"Breach reported: {breach_id} — {request.breach_type} ({request.severity})",
        details={
            "breach_id": breach_id,
            "severity": request.severity,
            "affected_count": len(request.affected_patient_ids),
        },
        user_id=current_user.id,
        db=db,
    )

    return {
        "breach_id": breach_id,
        "status": "DETECTED",
        "detected_at": breach.detected_at.isoformat(),
        "board_report_deadline": breach.board_report_deadline.isoformat(),
        "message": "Breach reported. 72-hour board report deadline initiated.",
    }


@router.post("/breaches/{breach_id}/notify-board")
async def notify_board(
    breach_id: str,
    current_user = Depends(require_permission("system.admin")),
    db: AsyncSession = Depends(get_db),
):
    """Notify Data Protection Board of breach (DPDP Section 8.3)."""
    result = await db.execute(
        select(DataBreach).where(DataBreach.breach_id == breach_id)
    )
    breach = result.scalar_one_or_none()
    if not breach:
        raise HTTPException(status_code=404, detail="Breach not found")

    breach.board_notified = True
    breach.board_notified_at = datetime.utcnow()
    breach.status = BreachStatus.INVESTIGATING

    await log_action(
        action=AuditAction.BREACH_NOTIFIED,
        description=f"Board notified: {breach_id}",
        details={"breach_id": breach_id},
        user_id=current_user.id,
        db=db,
    )

    return {"breach_id": breach_id, "board_notified": True, "board_notified_at": breach.board_notified_at.isoformat()}


# ── Erasure Schedule (DPDP Section 8.5) ──

@router.get("/erasure-schedule")
async def list_erasure_schedule(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """List scheduled data erasures."""
    query = select(ErasureSchedule).order_by(ErasureSchedule.scheduled_date)
    if status:
        query = query.where(ErasureSchedule.execution_status == status)
    query = query.limit(limit)

    result = await db.execute(query)
    schedules = result.scalars().all()

    return [
        {
            "patient_id": s.patient_id,
            "erasure_type": s.erasure_type,
            "reason": s.erasure_reason,
            "scheduled_date": s.scheduled_date.isoformat(),
            "notified_at": s.notified_at.isoformat() if s.notified_at else None,
            "user_responded": s.user_responded,
            "executed_at": s.executed_at.isoformat() if s.executed_at else None,
            "execution_status": s.execution_status,
            "records_affected": s.records_affected,
        }
        for s in schedules
    ]


# ── Data Principal Requests ──

@router.get("/data-principal-requests")
async def list_requests(
    status_filter: Optional[str] = Query(None),
    request_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """List data principal rights requests."""
    query = select(DataPrincipalRequest).order_by(DataPrincipalRequest.filed_at.desc())
    if status_filter:
        query = query.where(DataPrincipalRequest.status == status_filter)
    if request_type:
        query = query.where(DataPrincipalRequest.request_type == request_type)
    query = query.limit(limit)

    result = await db.execute(query)
    requests = result.scalars().all()

    return [
        {
            "request_id": r.id,
            "patient_id": r.patient_id,
            "request_type": r.request_type,
            "status": r.status,
            "filed_at": r.filed_at.isoformat(),
            "sla_deadline": r.sla_deadline.isoformat() if r.sla_deadline else None,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "rejection_reason": r.rejection_reason,
        }
        for r in requests
    ]


# ── Audit Log (DPDP Section 8.6 — 1-year retention) ──

@router.get("/audit-log")
async def get_audit_logs(
    action_filter: Optional[str] = Query(None),
    patient_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get audit log entries with filters."""
    query = select(AuditLog).order_by(AuditLog.timestamp.desc())

    if action_filter:
        try:
            act = AuditAction(action_filter)
            query = query.where(AuditLog.action == act)
        except ValueError:
            pass
    if patient_id:
        query = query.where(AuditLog.patient_id == patient_id)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "total": len(logs),
        "offset": offset,
        "limit": limit,
        "entries": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "action": log.action.value if log.action else None,
                "patient_id": log.patient_id,
                "resource_id": log.resource_id,
                "resource_type": log.resource_type,
                "user_id": log.user_id,
                "ip_address": log.ip_address,
                "description": log.description,
                "details": log.details_json,
                "consent_id": log.consent_id,
                "retention_until": log.retention_until.isoformat() if log.retention_until else None,
            }
            for log in logs
        ],
    }


# ── DPDP Compliance Report ──

@router.get("/report")
async def get_compliance_report(current_user = Depends(require_permission("audit.view"))):
    """Generate DPDP 2025 compliance status report."""
    report = compliance.generate_compliance_report()
    return report
