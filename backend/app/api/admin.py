"""HealthBridge Platform — Admin API Routes"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db, AsyncSession
from app.models import User, UserRole, Patient, PatientRecord, DataBreach
from app.security.auth import hash_password
from app.security.rbac import require_permission
from app.services.dpdp_compliance import DpdpComplianceService
from sqlalchemy import select, func

router = APIRouter(prefix="/api/v1/admin", tags=["Administration"])
compliance = DpdpComplianceService()


# ── Schemas ──

class CreateUserRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "READ_ONLY"

class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


# ── User Management ──

@router.get("/users")
async def list_users(
    current_user = Depends(require_permission("user.manage")),
    db: AsyncSession = Depends(get_db),
):
    """List all platform users."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.value if u.role else None,
            "is_active": u.is_active,
            "is_locked": u.is_locked,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    current_user = Depends(require_permission("user.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new platform user."""
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        role = UserRole(request.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")

    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        role=role,
    )
    db.add(user)
    await db.flush()

    return {"id": user.id, "email": user.email, "role": user.role.value, "created": True}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    current_user = Depends(require_permission("user.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's details."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.full_name is not None:
        user.full_name = request.full_name
    if request.role is not None:
        try:
            user.role = UserRole(request.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")
    if request.is_active is not None:
        user.is_active = request.is_active

    await db.flush()
    return {"id": user.id, "email": user.email, "role": user.role.value, "updated": True}


# ── DPDP Compliance Operations ──

@router.post("/dpia")
async def conduct_dpia(current_user = Depends(require_permission("system.admin"))):
    """Conduct Data Protection Impact Assessment (DPDP Section 16 — SDF)."""
    dpia = compliance.conduct_dpia()
    return dpia


@router.post("/purge-audit-logs")
async def purge_audit_logs(
    retention_days: int = 365,
    current_user = Depends(require_permission("system.admin")),
):
    """Purge audit logs older than specified days (DPDP Section 8.6)."""
    from app.security.audit import purge_audit_logs
    from datetime import date

    before_date = date.today() - timedelta(days=retention_days)
    count = await purge_audit_logs(before_date)

    return {
        "purged_count": count,
        "retention_days": retention_days,
        "cutoff_date": before_date.isoformat(),
        "message": f"{count} audit log entries purged",
    }


@router.post("/schedule-erasure/{patient_id}")
async def schedule_patient_erasure(
    patient_id: str,
    request: Request,
    current_user = Depends(require_permission("system.admin")),
    db: AsyncSession = Depends(get_db),
):
    """Schedule erasure of a patient's data (DPDP Section 8.5)."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Check clinical retention requirement
    exemption = compliance.check_clinical_establishment_exemption(patient_id)

    erasure = compliance.schedule_erasure(
        patient_id=patient_id,
        reason="user_request" if not exemption.get("is_exempt") else "clinical_retention_expired",
        erasure_type="PARTIAL" if exemption.get("is_exempt") else "FULL",
    )

    return erasure


# ── Stats ──

@router.get("/stats")
async def get_admin_stats(
    current_user = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get platform statistics for admin dashboard."""
    # Patient count
    patient_count = (await db.execute(select(func.count(Patient.id)))).scalar()
    # Record count
    record_count = (await db.execute(select(func.count(PatientRecord.id)))).scalar()
    # Active breaches
    active_breaches = (await db.execute(
        select(func.count(DataBreach.id)).where(DataBreach.status.in_(["DETECTED", "INVESTIGATING"]))
    )).scalar()
    # User count
    user_count = (await db.execute(select(func.count(User.id)))).scalar()

    from app.models import DataPrincipalRequest
    pending_requests = (await db.execute(
        select(func.count(DataPrincipalRequest.id)).where(DataPrincipalRequest.status == "PENDING")
    )).scalar()

    return {
        "total_patients": patient_count,
        "total_records": record_count,
        "active_breaches": active_breaches,
        "total_users": user_count,
        "pending_dp_requests": pending_requests,
        "timestamp": datetime.utcnow().isoformat(),
    }
