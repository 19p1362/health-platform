"""
HealthBridge Platform — OPD Registration & Token Queue API Routes

Day 3: OPD Registration + UHID + Token Queue
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from enum import Enum
import uuid

from app.database import get_db, AsyncSession
from app.models import Patient, User, Organization, ConsentStatus, Gender
from app.security.rbac import require_permission
from app.security.audit import log_action
from app.security.encryption import encrypt_field, decrypt_field, mask_field
from sqlalchemy import select, func, and_, Column, String, Integer, DateTime, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import selectinload, relationship

router = APIRouter(prefix="/api/v1/opd", tags=["OPD Registration"])


# ═══════════════════════════════════════════════════════════════
# Enums & Schemas
# ═══════════════════════════════════════════════════════════════

class VisitType(str, Enum):
    NEW = "NEW"
    FOLLOWUP = "FOLLOWUP"
    EMERGENCY = "EMERGENCY"
    REFERRAL = "REFERRAL"


class TokenStatus(str, Enum):
    WAITING = "WAITING"
    CALLED = "CALLED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class OPDRegistrationRequest(BaseModel):
    """Walk-in patient registration for OPD."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: Optional[str] = None
    gender: str = Field(default="UNKNOWN", pattern="^(MALE|FEMALE|OTHER|UNKNOWN)$")
    phone: Optional[str] = Field(None, pattern=r"^\+?[0-9\s\-\(\)]{10,15}$")
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    blood_group: Optional[str] = None
    chronic_conditions: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    visit_type: VisitType = VisitType.NEW
    referred_by: Optional[str] = None


class TokenQueueResponse(BaseModel):
    token_id: str
    token_number: int
    patient_id: str
    patient_name: str
    uhid: str
    visit_type: str
    status: str
    queue_position: int
    estimated_wait_minutes: int
    created_at: str
    called_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class OPDRegistrationResponse(BaseModel):
    patient_id: str
    uhid: str
    mrn: str
    token: TokenQueueResponse
    message: str


class TokenActionRequest(BaseModel):
    """Action to perform on a token."""
    action: str = Field(..., pattern="^(call|start|complete|skip|cancel)$")
    doctor_id: Optional[str] = None
    notes: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# UHID Generator
# ═══════════════════════════════════════════════════════════════

async def get_next_uhid_sequence(db: AsyncSession, tenant_id: str) -> int:
    """Get next UHID sequence number for today for this organization."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)
    
    result = await db.execute(
        select(func.count(Patient.id))
        .where(
            Patient.tenant_id == tenant_id,
            Patient.created_at >= today_start,
            Patient.created_at <= today_end
        )
    )
    count = result.scalar() or 0
    return count + 1


async def generate_formatted_uhid(db: AsyncSession, tenant_id: str) -> str:
    """Generate formatted UHID with org slug and sequence."""
    org_result = await db.execute(select(Organization).where(Organization.id == tenant_id))
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    org_slug = org.slug.upper()[:6]
    seq = await get_next_uhid_sequence(db, tenant_id)
    today = datetime.now().strftime("%Y%m%d")
    return f"UHID-{org_slug}-{today}-{seq:04d}"


async def get_next_token_number(db: AsyncSession, tenant_id: str) -> int:
    """Get next token number for today."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)
    
    # Import the model from models
    from app.models import OPDTokenQueue
    
    result = await db.execute(
        select(func.max(OPDTokenQueue.token_number))
        .where(
            OPDTokenQueue.tenant_id == tenant_id,
            OPDTokenQueue.created_at >= today_start,
            OPDTokenQueue.created_at <= today_end
        )
    )
    max_token = result.scalar() or 0
    return max_token + 1


# ═══════════════════════════════════════════════════════════════
# OPD Registration Routes
# ═══════════════════════════════════════════════════════════════

@router.post("/register", response_model=OPDRegistrationResponse, status_code=201)
async def register_opd_patient(
    request: OPDRegistrationRequest,
    req: Request,
    current_user = Depends(require_permission("patient.write")),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a walk-in patient for OPD visit.
    
    Creates:
    1. Patient record with encrypted PII
    2. Generates UHID (Unique Health ID)
    3. Creates token queue entry
    4. Returns token with queue position
    """
    tenant_id = current_user.tenant_id
    
    # Parse date of birth
    dob = None
    age = None
    if request.date_of_birth:
        try:
            dob = date.fromisoformat(request.date_of_birth)
            age = datetime.now().year - dob.year
        except ValueError:
            pass
    
    # Generate UHID
    uhid = await generate_formatted_uhid(db, tenant_id)
    
    # Generate MRN
    mrn = f"OPD-{uuid.uuid4().hex[:8].upper()}"
    
    # Create patient
    patient = Patient(
        mrn=mrn,
        uhid=uhid,
        first_name=encrypt_field(request.first_name),
        last_name=encrypt_field(request.last_name),
        date_of_birth=dob,
        gender=Gender(request.gender) if request.gender else Gender.UNKNOWN,
        phone=encrypt_field(request.phone) if request.phone else None,
        email=encrypt_field(request.email) if request.email else None,
        address=encrypt_field(request.address) if request.address else None,
        age_years=age,
        city=request.city,
        state=request.state,
        pincode=request.pincode,
        blood_group=request.blood_group,
        chronic_conditions=request.chronic_conditions,
        emergency_contact_name=request.emergency_contact_name,
        emergency_contact_phone=encrypt_field(request.emergency_contact_phone) if request.emergency_contact_phone else None,
        consent_status=ConsentStatus.PENDING,
        tenant_id=tenant_id,
        created_by=current_user.id,
    )
    db.add(patient)
    await db.flush()
    
    # Get next token number
    token_number = await get_next_token_number(db, tenant_id)
    
    # Import token queue model
    from app.models import OPDTokenQueue
    
    # Create token queue entry
    token = OPDTokenQueue(
        token_number=token_number,
        patient_id=patient.id,
        tenant_id=tenant_id,
        visit_type=request.visit_type,
        status=TokenStatus.WAITING,
        queue_position=token_number,  # Simple position = token number for now
        estimated_wait_minutes=token_number * 5,  # 5 min per patient estimate
    )
    db.add(token)
    await db.flush()
    
    # Calculate queue position (how many waiting ahead)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    waiting_result = await db.execute(
        select(func.count(OPDTokenQueue.id))
        .where(
            OPDTokenQueue.tenant_id == tenant_id,
            OPDTokenQueue.status == TokenStatus.WAITING,
            OPDTokenQueue.created_at >= today_start,
            OPDTokenQueue.token_number < token_number
        )
    )
    queue_position = waiting_result.scalar() or 0
    token.queue_position = queue_position
    
    # Audit log
    await log_action(
        action="OPD_REGISTRATION",
        patient_id=patient.id,
        user_id=current_user.id,
        description=f"OPD registration: {request.first_name} {request.last_name} (UHID: {uhid}, Token: {token_number})",
        db=db
    )
    
    # Return response
    patient_name = f"{request.first_name} {request.last_name}"
    
    return OPDRegistrationResponse(
        patient_id=patient.id,
        uhid=uhid,
        mrn=mrn,
        token=TokenQueueResponse(
            token_id=token.id,
            token_number=token.token_number,
            patient_id=patient.id,
            patient_name=patient_name,
            uhid=uhid,
            visit_type=request.visit_type.value,
            status=token.status.value,
            queue_position=token.queue_position,
            estimated_wait_minutes=token.estimated_wait_minutes,
            created_at=token.created_at.isoformat(),
        ),
        message=f"Patient registered successfully. UHID: {uhid}, Token: {token_number}"
    )


@router.get("/tokens", response_model=list[TokenQueueResponse])
async def list_tokens(
    status: Optional[TokenStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """List OPD tokens for today."""
    from app.models import OPDTokenQueue
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)
    
    query = select(OPDTokenQueue).where(
        OPDTokenQueue.tenant_id == current_user.tenant_id,
        OPDTokenQueue.created_at >= today_start,
        OPDTokenQueue.created_at <= today_end
    )
    
    if status:
        query = query.where(OPDTokenQueue.status == status)
    
    query = query.order_by(OPDTokenQueue.token_number).offset(offset).limit(limit)
    result = await db.execute(query)
    tokens = result.scalars().all()
    
    # Build response with patient names
    response = []
    for token in tokens:
        patient = await db.get(Patient, token.patient_id)
        patient_name = f"{decrypt_field(patient.first_name)} {decrypt_field(patient.last_name)}" if patient else "Unknown"
        response.append(TokenQueueResponse(
            token_id=token.id,
            token_number=token.token_number,
            patient_id=token.patient_id,
            patient_name=patient_name,
            uhid=patient.uhid if patient else "",
            visit_type=token.visit_type.value,
            status=token.status.value,
            queue_position=token.queue_position,
            estimated_wait_minutes=token.estimated_wait_minutes,
            created_at=token.created_at.isoformat(),
            called_at=token.called_at.isoformat() if token.called_at else None,
            started_at=token.started_at.isoformat() if token.started_at else None,
            completed_at=token.completed_at.isoformat() if token.completed_at else None,
        ))
    
    return response


@router.get("/tokens/{token_id}", response_model=TokenQueueResponse)
async def get_token(
    token_id: str,
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get token details by ID."""
    from app.models import OPDTokenQueue
    
    token = await db.get(OPDTokenQueue, token_id)
    if not token or token.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Token not found")
    
    patient = await db.get(Patient, token.patient_id)
    patient_name = f"{decrypt_field(patient.first_name)} {decrypt_field(patient.last_name)}" if patient else "Unknown"
    
    return TokenQueueResponse(
        token_id=token.id,
        token_number=token.token_number,
        patient_id=token.patient_id,
        patient_name=patient_name,
        uhid=patient.uhid if patient else "",
        visit_type=token.visit_type.value,
        status=token.status.value,
        queue_position=token.queue_position,
        estimated_wait_minutes=token.estimated_wait_minutes,
        created_at=token.created_at.isoformat(),
        called_at=token.called_at.isoformat() if token.called_at else None,
        started_at=token.started_at.isoformat() if token.started_at else None,
        completed_at=token.completed_at.isoformat() if token.completed_at else None,
    )


@router.post("/tokens/{token_id}/action")
async def token_action(
    token_id: str,
    request: TokenActionRequest,
    req: Request,
    current_user = Depends(require_permission("patient.write")),
    db: AsyncSession = Depends(get_db),
):
    """Perform action on token: call, start, complete, skip, cancel."""
    from app.models import OPDTokenQueue
    
    token = await db.get(OPDTokenQueue, token_id)
    if not token or token.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Token not found")
    
    action = request.action.lower()
    now = datetime.now()
    
    if action == "call":
        if token.status != TokenStatus.WAITING:
            raise HTTPException(status_code=400, detail="Token must be in WAITING status to call")
        token.status = TokenStatus.CALLED
        token.called_at = now
        token.doctor_id = request.doctor_id or current_user.id
        
    elif action == "start":
        if token.status not in (TokenStatus.WAITING, TokenStatus.CALLED):
            raise HTTPException(status_code=400, detail="Token must be WAITING or CALLED to start")
        token.status = TokenStatus.IN_PROGRESS
        token.started_at = now
        token.doctor_id = request.doctor_id or current_user.id
        
    elif action == "complete":
        if token.status != TokenStatus.IN_PROGRESS:
            raise HTTPException(status_code=400, detail="Token must be IN_PROGRESS to complete")
        token.status = TokenStatus.COMPLETED
        token.completed_at = now
        token.notes = request.notes
        
    elif action == "skip":
        token.status = TokenStatus.SKIPPED
        token.completed_at = now
        token.notes = request.notes
        
    elif action == "cancel":
        token.status = TokenStatus.CANCELLED
        token.completed_at = now
        token.notes = request.notes
        
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    await db.flush()
    
    # Audit log
    await log_action(
        action=f"TOKEN_{action.upper()}",
        patient_id=token.patient_id,
        user_id=current_user.id,
        description=f"Token {token.token_number} {action}ed",
        db=db
    )
    
    # Recalculate queue positions for waiting tokens
    await recalculate_queue_positions(db, current_user.tenant_id)
    
    return {"message": f"Token {action}ed successfully", "token_id": token.id, "new_status": token.status.value}


@router.get("/dashboard")
async def opd_dashboard(
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """OPD dashboard with today's statistics."""
    from app.models import OPDTokenQueue
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)
    
    # Total registered today
    total_result = await db.execute(
        select(func.count(OPDTokenQueue.id))
        .where(
            OPDTokenQueue.tenant_id == current_user.tenant_id,
            OPDTokenQueue.created_at >= today_start,
            OPDTokenQueue.created_at <= today_end
        )
    )
    total_today = total_result.scalar() or 0
    
    # By status
    status_result = await db.execute(
        select(OPDTokenQueue.status, func.count(OPDTokenQueue.id))
        .where(
            OPDTokenQueue.tenant_id == current_user.tenant_id,
            OPDTokenQueue.created_at >= today_start,
            OPDTokenQueue.created_at <= today_end
        )
        .group_by(OPDTokenQueue.status)
    )
    by_status = {status.value: count for status, count in status_result.all()}
    
    # Average wait time (completed tokens)
    wait_result = await db.execute(
        select(func.avg(
            func.extract('epoch', OPDTokenQueue.completed_at - OPDTokenQueue.created_at) / 60
        ))
        .where(
            OPDTokenQueue.tenant_id == current_user.tenant_id,
            OPDTokenQueue.status == TokenStatus.COMPLETED,
            OPDTokenQueue.created_at >= today_start,
            OPDTokenQueue.created_at <= today_end
        )
    )
    avg_wait = wait_result.scalar() or 0
    
    # Next token number
    next_token = await get_next_token_number(db, current_user.tenant_id)
    
    return {
        "date": today_start.date().isoformat(),
        "total_registered": total_today,
        "waiting": by_status.get("WAITING", 0),
        "called": by_status.get("CALLED", 0),
        "in_progress": by_status.get("IN_PROGRESS", 0),
        "completed": by_status.get("COMPLETED", 0),
        "skipped": by_status.get("SKIPPED", 0),
        "cancelled": by_status.get("CANCELLED", 0),
        "by_status": by_status,
        "average_wait_minutes": round(avg_wait, 1),
        "next_token_number": next_token,
    }


async def recalculate_queue_positions(db: AsyncSession, tenant_id: str):
    """Recalculate queue positions for all waiting tokens."""
    from app.models import OPDTokenQueue
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    waiting_tokens = await db.execute(
        select(OPDTokenQueue)
        .where(
            OPDTokenQueue.tenant_id == tenant_id,
            OPDTokenQueue.status == TokenStatus.WAITING,
            OPDTokenQueue.created_at >= today_start
        )
        .order_by(OPDTokenQueue.token_number)
    )
    tokens = waiting_tokens.scalars().all()
    
    for i, token in enumerate(tokens):
        token.queue_position = i + 1
    
    await db.flush()


# ═══════════════════════════════════════════════════════════════
# Search existing patient for OPD visit
# ═══════════════════════════════════════════════════════════════

@router.get("/search-patient")
async def search_patient_for_opd(
    q: str = Query(..., min_length=2),
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Search patients by name, UHID, MRN, or phone for OPD registration."""
    query = select(Patient).where(
        Patient.tenant_id == current_user.tenant_id
    )
    
    conditions = []
    if q.isdigit() and len(q) == 10:
        conditions.append(Patient.phone.ilike(f"%{q}%"))
    else:
        conditions.append(Patient.first_name.ilike(f"%{q}%"))
        conditions.append(Patient.last_name.ilike(f"%{q}%"))
        conditions.append(Patient.uhid.ilike(f"%{q}%"))
        conditions.append(Patient.mrn.ilike(f"%{q}%"))
    
    if conditions:
        from sqlalchemy import or_
        query = query.where(or_(*conditions))
    
    query = query.limit(20)
    result = await db.execute(query)
    patients = result.scalars().all()
    
    return [
        {
            "patient_id": p.id,
            "uhid": p.uhid,
            "mrn": p.mrn,
            "name": f"{decrypt_field(p.first_name)} {decrypt_field(p.last_name)}",
            "gender": p.gender.value if p.gender else None,
            "age": p.age_years,
            "phone": mask_field(decrypt_field(p.phone)) if p.phone else None,
        }
        for p in patients
    ]


@router.post("/existing-patient/{patient_id}/token", response_model=OPDRegistrationResponse)
async def create_token_for_existing_patient(
    patient_id: str,
    visit_type: VisitType = VisitType.FOLLOWUP,
    referred_by: Optional[str] = None,
    current_user = Depends(require_permission("patient.write")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new OPD token for an existing patient (follow-up visit)."""
    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Get next token number
    token_number = await get_next_token_number(db, current_user.tenant_id)
    
    from app.models import OPDTokenQueue
    
    token = OPDTokenQueue(
        token_number=token_number,
        patient_id=patient.id,
        tenant_id=current_user.tenant_id,
        visit_type=visit_type,
        status=TokenStatus.WAITING,
        queue_position=0,  # Will be recalculated
        estimated_wait_minutes=0,
    )
    db.add(token)
    await db.flush()
    
    # Recalculate queue positions
    await recalculate_queue_positions(db, current_user.tenant_id)
    
    # Audit log
    await log_action(
        action="OPD_FOLLOWUP_TOKEN",
        patient_id=patient.id,
        user_id=current_user.id,
        description=f"Follow-up token created for existing patient (Token: {token_number})",
        db=db
    )
    
    return OPDRegistrationResponse(
        patient_id=patient.id,
        uhid=patient.uhid,
        mrn=patient.mrn,
        token=TokenQueueResponse(
            token_id=token.id,
            token_number=token.token_number,
            patient_id=patient.id,
            patient_name=f"{decrypt_field(patient.first_name)} {decrypt_field(patient.last_name)}",
            uhid=patient.uhid,
            visit_type=visit_type.value,
            status=token.status.value,
            queue_position=token.queue_position,
            estimated_wait_minutes=token.estimated_wait_minutes,
            created_at=token.created_at.isoformat(),
        ),
        message=f"Follow-up token created. Token: {token_number}"
    )