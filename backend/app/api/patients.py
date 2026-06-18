"""HealthBridge Platform — Patient API Routes"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

from app.database import get_db, AsyncSession
from app.models import Patient, PatientRecord, ConsentStatus, Gender, RecordType, AuditAction
from app.security.rbac import require_permission
from app.security.audit import log_action
from app.security.encryption import encrypt_field, decrypt_field, mask_field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/api/v1/patients", tags=["Patients"])


# ── Schemas ──

class PatientSearchParams(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    mrn: Optional[str] = None
    phone: Optional[str] = None
    search_external: bool = True

class PatientResponse(BaseModel):
    patient_id: str
    mrn: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    consent_status: str
    source_count: int
    abha_number: Optional[str] = None

class PatientDetailResponse(BaseModel):
    patient_id: str
    mrn: str
    demographics: dict
    consent_status: str
    consent_purposes: list
    sources: list
    counts: dict
    abha_number: Optional[str] = None
    blood_group: Optional[str] = None
    chronic_conditions: Optional[str] = None

class CreatePatientRequest(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = "UNKNOWN"
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    mrn: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    blood_group: Optional[str] = None
    chronic_conditions: Optional[str] = None


# ── Routes ──

@router.get("/search", response_model=list[PatientResponse])
async def search_patients(
    request: Request,
    first_name: Optional[str] = Query(None),
    last_name: Optional[str] = Query(None),
    mrn: Optional[str] = Query(None),
    phone: Optional[str] = Query(None),
    search_external: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Search patients across local records. All searches are logged for DPDP compliance."""
    query = select(Patient)

    conditions = []
    if first_name:
        conditions.append(Patient.first_name.ilike(f"%{first_name}%"))
    if last_name:
        conditions.append(Patient.last_name.ilike(f"%{last_name}%"))
    if mrn:
        conditions.append(Patient.mrn.ilike(f"%{mrn}%"))
    if phone:
        conditions.append(Patient.phone.ilike(f"%{phone}%"))

    if conditions:
        query = query.where(or_(*conditions))

    query = query.offset(offset).limit(limit).order_by(Patient.updated_at.desc())
    result = await db.execute(query)
    patients = result.scalars().all()

    # Audit log the search
    search_params = {k: v for k, v in {
        "first_name": first_name, "last_name": last_name,
        "mrn": mask_field(mrn) if mrn else None,
        "phone": mask_field(phone) if phone else None,
    }.items() if v}
    await log_action(
        action=AuditAction.PATIENT_ACCESSED,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        description=f"Patient search: {len(patients)} results",
        details={"search_params": search_params, "result_count": len(patients)},
        db=db
    )

    return [
        PatientResponse(
            patient_id=p.id,
            mrn=p.mrn,
            first_name=decrypt_field(p.first_name),
            last_name=decrypt_field(p.last_name),
            gender=p.gender.value if p.gender else None,
            age=p.age_years,
            consent_status=p.consent_status.value if p.consent_status else "UNKNOWN",
            source_count=len(p.accounts) if p.accounts else 0,
            abha_number=p.abha_number,
        )
        for p in patients
    ]


@router.get("/{patient_id}", response_model=PatientDetailResponse)
async def get_patient(
    patient_id: str,
    request: Request,
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed patient record with all sources and record counts."""
    result = await db.execute(
        select(Patient)
        .options(selectinload(Patient.accounts))
        .where(Patient.id == patient_id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get record counts
    count_result = await db.execute(
        select(PatientRecord.record_type, func.count().label("cnt"))
        .where(PatientRecord.patient_id == patient_id, PatientRecord.is_active)
        .group_by(PatientRecord.record_type)
    )
    counts = {row.record_type.value if hasattr(row.record_type, 'value') else str(row.record_type): row.cnt
              for row in count_result.all()}

    # Build sources from patient accounts
    sources = []
    if patient.accounts:
        for acct in patient.accounts:
            sources.append({
                "source_system": acct.source_system,
                "source_type": acct.source_type.value if hasattr(acct.source_type, 'value') else str(acct.source_type),
                "external_id": mask_field(acct.external_id),
                "verified": acct.is_verified,
                "last_sync": acct.last_sync.isoformat() if acct.last_sync else None,
                "real_time_connected": acct.real_time_connected,
            })

    # Audit log
    await log_action(
        action=AuditAction.PATIENT_ACCESSED,
        patient_id=patient_id,
        user_id=current_user.id,
        description=f"Patient record accessed: {decrypt_field(patient.first_name)} {decrypt_field(patient.last_name)}",
        db=db
    )

    return PatientDetailResponse(
        patient_id=patient.id,
        mrn=patient.mrn,
        demographics={
            "first_name": decrypt_field(patient.first_name),
            "last_name": decrypt_field(patient.last_name),
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "gender": patient.gender.value if patient.gender else None,
            "phone": mask_field(decrypt_field(patient.phone)) if patient.phone else None,
            "email": patient.email,
            "city": patient.city,
            "state": patient.state,
        },
        consent_status=patient.consent_status.value if patient.consent_status else "PENDING",
        consent_purposes=patient.consent_purposes or [],
        sources=sources,
        counts=counts,
        abha_number=patient.abha_number,
        blood_group=patient.blood_group,
        chronic_conditions=patient.chronic_conditions,
    )


@router.get("/{patient_id}/records")
async def get_patient_records(
    patient_id: str,
    record_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get clinical records for a patient."""
    query = select(PatientRecord).where(
        PatientRecord.patient_id == patient_id,
        PatientRecord.is_active
    )
    if record_type:
        try:
            rt = RecordType(record_type)
            query = query.where(PatientRecord.record_type == rt)
        except ValueError:
            pass

    query = query.order_by(PatientRecord.recorded_date.desc().nullslast()).offset(offset).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()

    return [
        {
            "id": r.id,
            "record_type": r.record_type.value if r.record_type else None,
            "source_system": r.source_system,
            "source_type": r.source_type.value if r.source_type else None,
            "clinical_summary": r.clinical_summary,
            "code": r.code,
            "code_system": r.code_system,
            "display_name": r.display_name,
            "recorded_date": r.recorded_date.isoformat() if r.recorded_date else None,
            "encounter_date": r.encounter_date.isoformat() if r.encounter_date else None,
            "provider_name": r.provider_name,
            "facility_name": r.facility_name,
        }
        for r in records
    ]


@router.post("/create", status_code=201)
async def create_patient(
    request: CreatePatientRequest,
    req: Request,
    current_user = Depends(require_permission("patient.write")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new patient record with encrypted PII."""
    import uuid
    mrn = request.mrn or f"HB-{uuid.uuid4().hex[:8].upper()}"

    dob = None
    age = None
    if request.date_of_birth:
        try:
            dob = date.fromisoformat(request.date_of_birth)
            age = datetime.now().year - dob.year
        except ValueError:
            pass

    patient = Patient(
        mrn=mrn,
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
        blood_group=request.blood_group,
        chronic_conditions=request.chronic_conditions,
        consent_status=ConsentStatus.PENDING,
    )
    db.add(patient)
    await db.flush()

    await log_action(
        action=AuditAction.DATA_INGESTED,
        patient_id=patient.id,
        user_id=current_user.id,
        description=f"Patient created: {request.first_name} {request.last_name} (MRN: {mrn})",
        db=db
    )

    return {
        "patient_id": patient.id,
        "mrn": mrn,
        "message": "Patient created successfully",
    }
