"""HealthBridge Platform — Consent Management API Routes (DPDP Sections 5-7)"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db, AsyncSession
from app.models import Patient, ConsentRecord, ConsentStatus, ConsentPurpose, AuditAction
from app.security.rbac import require_permission
from app.security.audit import log_action
from app.services.dpdp_compliance import DpdpComplianceService
from app.config import settings
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/consent", tags=["Consent Management"])
compliance = DpdpComplianceService()


# ── Schemas ──

class GrantConsentRequest(BaseModel):
    patient_id: str
    purpose: str  # TREATMENT, PAYMENT, OPERATIONS, RESEARCH, PUBLIC_HEALTH
    data_categories: list[str] = ["DEMOGRAPHICS", "CLINICAL"]
    duration_days: int = 365
    notice_language: str = "en"

class WithdrawConsentRequest(BaseModel):
    patient_id: str
    consent_id: str

class ConsentStatusResponse(BaseModel):
    consent_id: Optional[str] = None
    status: str
    purpose: Optional[str] = None
    data_categories: list[str] = []
    granted_at: Optional[str] = None
    expires_at: Optional[str] = None
    notice_provided: bool = False
    withdrawal_mechanism: Optional[str] = None


# ── Routes ──

@router.get("/status/{patient_id}")
async def get_consent_status(
    patient_id: str,
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get current consent status and all consent records for a patient."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get all consent records
    records_result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.patient_id == patient_id)
        .order_by(ConsentRecord.granted_at.desc())
    )
    consent_records = records_result.scalars().all()

    return {
        "patient_id": patient_id,
        "current_status": patient.consent_status.value if patient.consent_status else "PENDING",
        "active_consent_id": patient.consent_id,
        "purposes": patient.consent_purposes or [],
        "consent_expires_at": patient.consent_expires_at.isoformat() if patient.consent_expires_at else None,
        "consent_history": [
            {
                "consent_id": c.consent_id,
                "purpose": c.purpose.value if c.purpose else None,
                "data_categories": c.data_categories,
                "status": c.status.value if c.status else None,
                "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
                "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                "notice_language": c.notice_language,
                "notice_provided": c.notice_provided,
            }
            for c in consent_records
        ],
    }


@router.post("/grant")
async def grant_consent(
    request: GrantConsentRequest,
    req: Request,
    current_user = Depends(require_permission("consent.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Grant consent for data processing (DPDP Section 5-6)."""
    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == request.patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Validate purpose
    try:
        purpose = ConsentPurpose(request.purpose)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid purpose: {request.purpose}")

    # Generate consent notice
    import uuid
    consent_id = f"HB-CONSENT-{uuid.uuid4().hex[:12].upper()}"
    notice = compliance.generate_consent_notice(
        patient_id=request.patient_id,
        purposes=[request.purpose],
        data_categories=request.data_categories,
        duration_days=request.duration_days,
        language=request.notice_language,
    )

    expires_at = datetime.utcnow() + timedelta(days=request.duration_days)

    # Create consent record
    consent_record = ConsentRecord(
        consent_id=consent_id,
        patient_id=request.patient_id,
        purpose=purpose,
        data_categories=request.data_categories,
        duration_days=request.duration_days,
        status=ConsentStatus.GRANTED,
        granted_at=datetime.utcnow(),
        expires_at=expires_at,
        notice_provided=True,
        notice_language=request.notice_language,
        notice_text=notice.get("notice_text"),
        withdrawal_mechanism=f"POST /api/v1/consent/withdraw with consent_id={consent_id}",
    )
    db.add(consent_record)

    # Update patient record
    patient.consent_status = ConsentStatus.GRANTED
    patient.consent_id = consent_id
    if patient.consent_purposes:
        if purpose.value not in patient.consent_purposes:
            patient.consent_purposes.append(purpose.value)
    else:
        patient.consent_purposes = [purpose.value]
    patient.consent_granted_at = datetime.utcnow()
    patient.consent_expires_at = expires_at

    await db.flush()

    # Audit
    await log_action(
        action=AuditAction.CONSENT_GRANTED,
        patient_id=request.patient_id,
        user_id=current_user.id,
        description=f"Consent granted: {request.purpose} ({consent_id})",
        details={
            "consent_id": consent_id,
            "purpose": request.purpose,
            "data_categories": request.data_categories,
            "duration_days": request.duration_days,
        },
        consent_id=consent_id,
        ip_address=req.client.host if req.client else None,
        db=db,
    )

    return {
        "consent_id": consent_id,
        "status": "GRANTED",
        "purpose": request.purpose,
        "data_categories": request.data_categories,
        "expires_at": expires_at.isoformat(),
        "notice": notice,
        "withdrawal_endpoint": f"POST /api/v1/consent/withdraw with consent_id={consent_id}",
    }


@router.post("/withdraw")
async def withdraw_consent(
    request: WithdrawConsentRequest,
    req: Request,
    current_user = Depends(require_permission("consent.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Withdraw previously granted consent (DPDP Section 6 — withdrawal parity)."""
    # Find consent record
    result = await db.execute(
        select(ConsentRecord).where(
            ConsentRecord.consent_id == request.consent_id,
            ConsentRecord.patient_id == request.patient_id,
        )
    )
    consent = result.scalar_one_or_none()
    if not consent:
        raise HTTPException(status_code=404, detail="Consent record not found")

    if consent.status == ConsentStatus.WITHDRAWN:
        raise HTTPException(status_code=400, detail="Consent already withdrawn")

    # Update consent record
    consent.status = ConsentStatus.WITHDRAWN
    consent.previous_status = ConsentStatus.GRANTED
    consent.withdrawn_at = datetime.utcnow()

    # Update patient record
    patient_result = await db.execute(select(Patient).where(Patient.id == request.patient_id))
    patient = patient_result.scalar_one_or_none()
    if patient:
        patient.consent_status = ConsentStatus.WITHDRAWN
        patient.consent_id = None

    await db.flush()

    # Audit
    await log_action(
        action=AuditAction.CONSENT_WITHDRAWN,
        patient_id=request.patient_id,
        user_id=current_user.id,
        description=f"Consent withdrawn: {consent.purpose.value} ({request.consent_id})",
        details={"consent_id": request.consent_id},
        consent_id=request.consent_id,
        ip_address=req.client.host if req.client else None,
        db=db,
    )

    return {
        "consent_id": request.consent_id,
        "status": "WITHDRAWN",
        "withdrawn_at": consent.withdrawn_at.isoformat(),
        "message": "Consent withdrawn. No further processing of this patient's data will occur.",
    }


@router.get("/notice/{patient_id}")
async def get_consent_notice(
    patient_id: str,
    language: str = "en",
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Generate DPDP-compliant consent notice for a patient."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    notice = compliance.generate_consent_notice(
        patient_id=patient_id,
        purpose="TREATMENT",
        data_categories=["DEMOGRAPHICS", "CLINICAL", "LAB_REPORTS", "MEDICATIONS"],
        language=language,
    )

    return notice


@router.post("/data-principal-request")
async def file_data_principal_request(
    request: Request,
    current_user = Depends(require_permission("consent.manage")),
    db: AsyncSession = Depends(get_db),
):
    """File a data principal rights request (access, correction, erasure, grievance)."""
    body = await request.json()
    patient_id = body.get("patient_id")
    request_type = body.get("request_type")  # ACCESS, CORRECTION, ERASURE, GRIEVANCE
    details = body.get("details", {})

    from app.models import DataPrincipalRequest
    import uuid

    dp_request = DataPrincipalRequest(
        id=str(uuid.uuid4()),
        patient_id=patient_id,
        request_type=request_type,
        request_details=details,
        status="PENDING",
        filed_at=datetime.utcnow(),
        sla_deadline=datetime.utcnow() + timedelta(days=settings.DPDP_GRIEVANCE_SLA_DAYS),
    )
    db.add(dp_request)
    await db.flush()

    await log_action(
        action=AuditAction.DPDP_ACCESS_REQUEST if request_type == "ACCESS"
            else AuditAction.DPDP_CORRECTION_REQUEST if request_type == "CORRECTION"
            else AuditAction.DPDP_ERASURE_REQUEST if request_type == "ERASURE"
            else AuditAction.DPDP_GRIEVANCE_FILED,
        patient_id=patient_id,
        user_id=current_user.id,
        description=f"Data principal request filed: {request_type}",
        details={"request_type": request_type},
        db=db,
    )

    return {
        "request_id": dp_request.id,
        "status": "PENDING",
        "request_type": request_type,
        "sla_deadline": dp_request.sla_deadline.isoformat(),
    }
