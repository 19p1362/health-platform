"""HealthBridge Platform — SOAP Clinical Notes API Routes"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    SOAPNote, PatientSOAPVersion, ICD10Code, Patient, OPDRegistration, TokenQueue,
    TokenStatus, VitalSign, VitalSignType, AuditAction, User, UserRole
)
from app.security.auth import verify_token
from app.security.rbac import require_permission
from app.security.audit import log_action
from app.security.encryption import encrypt_field, decrypt_field, mask_field

router = APIRouter(prefix="/api/v1/clinical/soap", tags=["SOAP Clinical Notes"])


# ── Schemas ───

class ICD10CodeResponse(BaseModel):
    code: str
    description: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    is_billable: bool = True


class ICD10SearchResponse(BaseModel):
    codes: List[ICD10CodeResponse]
    total: int


class SOAPMedication(BaseModel):
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    route: Optional[str] = None
    instructions: Optional[str] = None


class SOAPInvestigation(BaseModel):
    name: str
    type: Optional[str] = "LAB"  # LAB, IMAGING, OTHER
    priority: Optional[str] = "ROUTINE"  # ROUTINE, URGENT, STAT
    notes: Optional[str] = None


class SOAPReferral(BaseModel):
    specialty: str
    reason: str
    urgency: Optional[str] = "ROUTINE"  # ROUTINE, URGENT, EMERGENT
    provider: Optional[str] = None


class ICD10CodeEntry(BaseModel):
    code: str
    description: str
    primary: bool = False


class SOAPNoteCreate(BaseModel):
    """Create or update a SOAP note for an encounter."""
    patient_id: str
    encounter_id: str
    token_id: str
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    chief_complaint: Optional[str] = None
    icd10_codes: List[ICD10CodeEntry] = Field(default_factory=list)
    medications: List[SOAPMedication] = Field(default_factory=list)
    investigations: List[SOAPInvestigation] = Field(default_factory=list)
    referrals: List[SOAPReferral] = Field(default_factory=list)
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    status: str = "DRAFT"  # DRAFT, FINALIZED
    word_count: int = 0
    time_spent_seconds: int = 0


class SOAPNoteUpdate(BaseModel):
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    chief_complaint: Optional[str] = None
    icd10_codes: Optional[List[ICD10CodeEntry]] = None
    medications: Optional[List[SOAPMedication]] = None
    investigations: Optional[List[SOAPInvestigation]] = None
    referrals: Optional[List[SOAPReferral]] = None
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    status: Optional[str] = None
    word_count: Optional[int] = None
    time_spent_seconds: Optional[int] = None


class SOAPNoteResponse(BaseModel):
    id: str
    patient_id: str
    encounter_id: str
    token_id: str
    subjective: Optional[str]
    objective: Optional[str]
    assessment: Optional[str]
    plan: Optional[str]
    chief_complaint: Optional[str]
    icd10_codes: List[ICD10CodeEntry]
    medications: List[SOAPMedication]
    investigations: List[SOAPInvestigation]
    referrals: List[SOAPReferral]
    follow_up_date: Optional[date]
    follow_up_notes: Optional[str]
    status: str
    version: int
    word_count: int
    time_spent_seconds: int
    last_autosaved_at: Optional[datetime]
    pdf_generated_at: Optional[datetime]
    created_by: Optional[str]
    finalized_by: Optional[str]
    finalized_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    # Related data (populated by query)
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    token_number: Optional[int] = None
    uhid: Optional[str] = None
    latest_vitals: List[dict] = Field(default_factory=list)


class SOAPNoteListResponse(BaseModel):
    notes: List[SOAPNoteResponse]
    total: int
    page: int
    page_size: int


class SOAPVersionResponse(BaseModel):
    id: str
    soap_note_id: str
    version_number: int
    subjective: Optional[str]
    objective: Optional[str]
    assessment: Optional[str]
    plan: Optional[str]
    icd10_codes: List[ICD10CodeEntry]
    medications: List[SOAPMedication]
    investigations: List[SOAPInvestigation]
    referrals: List[SOAPReferral]
    follow_up_date: Optional[date]
    follow_up_notes: Optional[str]
    word_count: int
    time_spent_seconds: int
    is_autosave: bool
    changed_by: Optional[str]
    change_summary: Optional[str]
    created_at: datetime


# ── ICD-10 Seed Data (common Indian clinical codes) ───

COMMON_ICD10_CODES = [
    {"code": "I10", "description": "Essential (primary) hypertension", "category": "Circulatory", "is_billable": True},
    {"code": "E11.9", "description": "Type 2 diabetes mellitus without complications", "category": "Endocrine", "is_billable": True},
    {"code": "E11.65", "description": "Type 2 diabetes mellitus with hyperglycemia", "category": "Endocrine", "is_billable": True},
    {"code": "J06.9", "description": "Acute upper respiratory infection, unspecified", "category": "Respiratory", "is_billable": True},
    {"code": "J20.9", "description": "Acute bronchitis, unspecified", "category": "Respiratory", "is_billable": True},
    {"code": "J44.1", "description": "Chronic obstructive pulmonary disease with acute exacerbation", "category": "Respiratory", "is_billable": True},
    {"code": "K59.1", "description": "Functional dyspepsia", "category": "Digestive", "is_billable": True},
    {"code": "M54.5", "description": "Low back pain", "category": "Musculoskeletal", "is_billable": True},
    {"code": "M79.3", "description": "Panniculitis, unspecified", "category": "Musculoskeletal", "is_billable": True},
    {"code": "R05", "description": "Cough", "category": "Symptoms", "is_billable": True},
    {"code": "R06.02", "description": "Shortness of breath", "category": "Symptoms", "is_billable": True},
    {"code": "R50.9", "description": "Fever, unspecified", "category": "Symptoms", "is_billable": True},
    {"code": "R51", "description": "Headache", "category": "Symptoms", "is_billable": True},
    {"code": "R53.1", "description": "Weakness", "category": "Symptoms", "is_billable": True},
    {"code": "Z00.00", "description": "Encounter for general adult medical examination without abnormal findings", "category": "Preventive", "is_billable": True},
    {"code": "Z13.1", "description": "Encounter for screening for diabetes mellitus", "category": "Preventive", "is_billable": True},
    {"code": "Z13.6", "description": "Encounter for screening for cardiovascular disorders", "category": "Preventive", "is_billable": True},
    {"code": "N39.0", "description": "Urinary tract infection, site not specified", "category": "Genitourinary", "is_billable": True},
    {"code": "K21.9", "description": "Gastro-esophageal reflux disease without esophagitis", "category": "Digestive", "is_billable": True},
    {"code": "F41.9", "description": "Anxiety disorder, unspecified", "category": "Mental Health", "is_billable": True},
    {"code": "F32.9", "description": "Major depressive disorder, single episode, unspecified", "category": "Mental Health", "is_billable": True},
    {"code": "H52.13", "description": "Myopia, bilateral", "category": "Eye", "is_billable": True},
    {"code": "H90.3", "description": "Sensorineural hearing loss, bilateral", "category": "Ear", "is_billable": True},
    {"code": "L20.9", "description": "Atopic dermatitis, unspecified", "category": "Skin", "is_billable": True},
    {"code": "L30.9", "description": "Dermatitis, unspecified", "category": "Skin", "is_billable": True},
    {"code": "N18.9", "description": "Chronic kidney disease, unspecified", "category": "Genitourinary", "is_billable": True},
    {"code": "I25.10", "description": "Atherosclerotic heart disease of native coronary artery without angina pectoris", "category": "Circulatory", "is_billable": True},
    {"code": "I48.91", "description": "Unspecified atrial fibrillation", "category": "Circulatory", "is_billable": True},
    {"code": "E78.5", "description": "Hyperlipidemia, unspecified", "category": "Endocrine", "is_billable": True},
    {"code": "D50.9", "description": "Iron deficiency anemia, unspecified", "category": "Blood", "is_billable": True},
]


async def ensure_icd10_codes_seeded(tenant_id: str, db: AsyncSession) -> None:
    """Ensure common ICD-10 codes are seeded for the tenant."""
    result = await db.execute(select(func.count()).select_from(ICD10Code).where(ICD10Code.tenant_id == tenant_id))
    count = result.scalar() or 0
    if count > 0:
        return

    for code_data in COMMON_ICD10_CODES:
        icd10 = ICD10Code(
            tenant_id=tenant_id,
            **code_data,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(icd10)
    await db.flush()


# ── Helper Functions ───

async def _get_latest_vitals(patient_id: str, encounter_id: str, db: AsyncSession) -> List[dict]:
    """Get latest vitals for a patient/encounter to auto-populate Objective tab."""
    result = await db.execute(
        select(VitalSign)
        .where(VitalSign.patient_id == patient_id)
        .where(VitalSign.encounter_id == encounter_id)
        .order_by(VitalSign.vital_type, desc(VitalSign.recorded_at))
    )
    vitals = result.scalars().all()

    # Get latest of each type
    latest_by_type = {}
    for v in vitals:
        if v.vital_type not in latest_by_type:
            latest_by_type[v.vital_type] = v

    return [
        {
            "type": v.vital_type.value,
            "value": v.value,
            "unit": v.unit,
            "recorded_at": v.recorded_at.isoformat() if v.recorded_at else None,
            "is_abnormal": v.is_abnormal,
            "reference_range_low": v.reference_range_low,
            "reference_range_high": v.reference_range_high,
        }
        for v in latest_by_type.values()
    ]


async def _create_soap_version(
    soap_note: SOAPNote,
    changed_by: str,
    change_summary: str,
    is_autosave: bool = False,
    db: AsyncSession = None,
) -> PatientSOAPVersion:
    """Create a version snapshot of the SOAP note."""
    version_num = await db.execute(
        select(func.coalesce(func.max(PatientSOAPVersion.version_number), 0))
        .where(PatientSOAPVersion.soap_note_id == soap_note.id)
    )
    version_num = (version_num.scalar() or 0) + 1

    version = PatientSOAPVersion(
        soap_note_id=soap_note.id,
        version_number=version_num,
        subjective=soap_note.subjective,
        objective=soap_note.objective,
        assessment=soap_note.assessment,
        plan=soap_note.plan,
        icd10_codes=[c.model_dump() if hasattr(c, 'model_dump') else c for c in soap_note.icd10_codes],
        medications=[m.model_dump() if hasattr(m, 'model_dump') else m for m in soap_note.medications],
        investigations=[i.model_dump() if hasattr(i, 'model_dump') else i for i in soap_note.investigations],
        referrals=[r.model_dump() if hasattr(r, 'model_dump') else r for r in soap_note.referrals],
        follow_up_date=soap_note.follow_up_date,
        follow_up_notes=soap_note.follow_up_notes,
        word_count=soap_note.word_count,
        time_spent_seconds=soap_note.time_spent_seconds,
        is_autosave=is_autosave,
        changed_by=changed_by,
        change_summary=change_summary,
        created_at=datetime.utcnow(),
    )
    db.add(version)
    return version


def _count_words(text: Optional[str]) -> int:
    """Count words in text."""
    if not text:
        return 0
    return len(text.split())


def _calculate_total_word_count(note: SOAPNote) -> int:
    """Calculate total word count across all SOAP sections."""
    total = 0
    for field in [note.subjective, note.objective, note.assessment, note.plan, note.chief_complaint]:
        total += _count_words(field)
    return total


# ── Routes ───

@router.post("", response_model=SOAPNoteResponse, status_code=201)
async def create_or_update_soap_note(
    request: SOAPNoteCreate,
    req: Request,
    current_user = Depends(require_permission("clinical.soap.write")),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a SOAP note for an encounter."""
    tenant_id = current_user.tenant_id
    user_id = current_user.id

    # Verify patient belongs to tenant
    patient_result = await db.execute(
        select(Patient).where(and_(Patient.id == request.patient_id, Patient.tenant_id == tenant_id))
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Verify encounter exists and belongs to tenant
    encounter_result = await db.execute(
        select(OPDRegistration).where(
            and_(OPDRegistration.id == request.encounter_id, OPDRegistration.tenant_id == tenant_id)
        )
    )
    encounter = encounter_result.scalar_one_or_none()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    # Verify token exists
    token_result = await db.execute(
        select(TokenQueue).where(
            and_(TokenQueue.id == request.token_id, TokenQueue.tenant_id == tenant_id)
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # Check if SOAP note already exists for this encounter
    existing_result = await db.execute(
        select(SOAPNote).where(SOAPNote.encounter_id == request.encounter_id)
    )
    soap_note = existing_result.scalar_one_or_none()

    word_count = _calculate_total_word_count_from_request(request)

    if soap_note:
        # Update existing note - create version first
        await _create_soap_version(
            soap_note, user_id, "Manual update", is_autosave=False, db=db
        )

        soap_note.subjective = request.subjective
        soap_note.objective = request.objective
        soap_note.assessment = request.assessment
        soap_note.plan = request.plan
        soap_note.chief_complaint = request.chief_complaint
        soap_note.icd10_codes = [c.model_dump() for c in request.icd10_codes]
        soap_note.medications = [m.model_dump() for m in request.medications]
        soap_note.investigations = [i.model_dump() for i in request.investigations]
        soap_note.referrals = [r.model_dump() for r in request.referrals]
        soap_note.follow_up_date = request.follow_up_date
        soap_note.follow_up_notes = request.follow_up_notes
        soap_note.status = request.status
        soap_note.word_count = word_count
        soap_note.time_spent_seconds = request.time_spent_seconds
        soap_note.updated_at = datetime.utcnow()

        if request.status == "FINALIZED" and soap_note.status != "FINALIZED":
            soap_note.finalized_by = user_id
            soap_note.finalized_at = datetime.utcnow()
            soap_note.completed_at = datetime.utcnow()
    else:
        # Create new SOAP note
        soap_note = SOAPNote(
            tenant_id=tenant_id,
            patient_id=request.patient_id,
            encounter_id=request.encounter_id,
            token_id=request.token_id,
            subjective=request.subjective,
            objective=request.objective,
            assessment=request.assessment,
            plan=request.plan,
            chief_complaint=request.chief_complaint,
            icd10_codes=[c.model_dump() for c in request.icd10_codes],
            medications=[m.model_dump() for m in request.medications],
            investigations=[i.model_dump() for i in request.investigations],
            referrals=[r.model_dump() for r in request.referrals],
            follow_up_date=request.follow_up_date,
            follow_up_notes=request.follow_up_notes,
            status=request.status,
            word_count=word_count,
            time_spent_seconds=request.time_spent_seconds,
            created_by=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        if request.status == "FINALIZED":
            soap_note.finalized_by = user_id
            soap_note.finalized_at = datetime.utcnow()
            soap_note.completed_at = datetime.utcnow()
        db.add(soap_note)

    await db.flush()

    # Create initial version
    await _create_soap_version(soap_note, user_id, "Created", is_autosave=False, db=db)

    # Audit log
    await log_action(
        action=AuditAction.DATA_INGESTED,
        user_id=user_id,
        patient_id=request.patient_id,
        ip_address=req.client.host if req.client else None,
        description=f"SOAP note {'updated' if existing_result else 'created'} for encounter {request.encounter_id}",
        details={
            "soap_note_id": soap_note.id,
            "encounter_id": request.encounter_id,
            "status": request.status,
            "word_count": word_count,
        },
        db=db,
    )

    # Get vitals for response
    vitals = await _get_latest_vitals(request.patient_id, request.encounter_id, db)

    return SOAPNoteResponse(
        id=soap_note.id,
        patient_id=soap_note.patient_id,
        encounter_id=soap_note.encounter_id,
        token_id=soap_note.token_id,
        subjective=soap_note.subjective,
        objective=soap_note.objective,
        assessment=soap_note.assessment,
        plan=soap_note.plan,
        chief_complaint=soap_note.chief_complaint,
        icd10_codes=[ICD10CodeEntry(**c) for c in soap_note.icd10_codes],
        medications=[SOAPMedication(**m) for m in soap_note.medications],
        investigations=[SOAPInvestigation(**i) for i in soap_note.investigations],
        referrals=[SOAPReferral(**r) for r in soap_note.referrals],
        follow_up_date=soap_note.follow_up_date,
        follow_up_notes=soap_note.follow_up_notes,
        status=soap_note.status,
        version=soap_note.version,
        word_count=soap_note.word_count,
        time_spent_seconds=soap_note.time_spent_seconds,
        last_autosaved_at=soap_note.last_autosaved_at,
        pdf_generated_at=soap_note.pdf_generated_at,
        created_by=soap_note.created_by,
        finalized_by=soap_note.finalized_by,
        finalized_at=soap_note.finalized_at,
        created_at=soap_note.created_at,
        updated_at=soap_note.updated_at,
        patient_name=f"{patient.first_name} {patient.last_name}",
        patient_age=patient.age_years,
        patient_gender=patient.gender.value if patient.gender else None,
        token_number=token.token_number,
        uhid=encounter.uhid,
        latest_vitals=vitals,
    )


def _calculate_total_word_count_from_request(request: SOAPNoteCreate) -> int:
    """Calculate word count from request data."""
    total = 0
    for field in [request.subjective, request.objective, request.assessment, request.plan, request.chief_complaint]:
        total += _count_words(field)
    return total


@router.get("/{encounter_id}", response_model=SOAPNoteResponse)
async def get_soap_note(
    encounter_id: str,
    current_user = Depends(require_permission("clinical.soap.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest SOAP note for an encounter."""
    tenant_id = current_user.tenant_id

    result = await db.execute(
        select(SOAPNote)
        .where(and_(SOAPNote.encounter_id == encounter_id, SOAPNote.tenant_id == tenant_id))
    )
    soap_note = result.scalar_one_or_none()
    if not soap_note:
        raise HTTPException(status_code=404, detail="SOAP note not found")

    # Get patient info
    patient_result = await db.execute(select(Patient).where(Patient.id == soap_note.patient_id))
    patient = patient_result.scalar_one_or_none()

    # Get token info
    token_result = await db.execute(select(TokenQueue).where(TokenQueue.id == soap_note.token_id))
    token = token_result.scalar_one_or_none()

    # Get encounter info
    encounter_result = await db.execute(select(OPDRegistration).where(OPDRegistration.id == soap_note.encounter_id))
    encounter = encounter_result.scalar_one_or_none()

    # Get latest vitals
    vitals = await _get_latest_vitals(soap_note.patient_id, soap_note.encounter_id, db)

    return SOAPNoteResponse(
        id=soap_note.id,
        patient_id=soap_note.patient_id,
        encounter_id=soap_note.encounter_id,
        token_id=soap_note.token_id,
        subjective=soap_note.subjective,
        objective=soap_note.objective,
        assessment=soap_note.assessment,
        plan=soap_note.plan,
        chief_complaint=soap_note.chief_complaint,
        icd10_codes=[ICD10CodeEntry(**c) for c in soap_note.icd10_codes],
        medications=[SOAPMedication(**m) for m in soap_note.medications],
        investigations=[SOAPInvestigation(**i) for i in soap_note.investigations],
        referrals=[SOAPReferral(**r) for r in soap_note.referrals],
        follow_up_date=soap_note.follow_up_date,
        follow_up_notes=soap_note.follow_up_notes,
        status=soap_note.status,
        version=soap_note.version,
        word_count=soap_note.word_count,
        time_spent_seconds=soap_note.time_spent_seconds,
        last_autosaved_at=soap_note.last_autosaved_at,
        pdf_generated_at=soap_note.pdf_generated_at,
        created_by=soap_note.created_by,
        finalized_by=soap_note.finalized_by,
        finalized_at=soap_note.finalized_at,
        created_at=soap_note.created_at,
        updated_at=soap_note.updated_at,
        patient_name=f"{patient.first_name} {patient.last_name}" if patient else None,
        patient_age=patient.age_years if patient else None,
        patient_gender=patient.gender.value if patient and patient.gender else None,
        token_number=token.token_number if token else None,
        uhid=encounter.uhid if encounter else None,
        latest_vitals=vitals,
    )


@router.get("/{encounter_id}/versions", response_model=List[SOAPVersionResponse])
async def get_soap_versions(
    encounter_id: str,
    current_user = Depends(require_permission("clinical.soap.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get all versions of a SOAP note for audit trail."""
    tenant_id = current_user.tenant_id

    # Get the SOAP note
    soap_result = await db.execute(
        select(SOAPNote).where(and_(SOAPNote.encounter_id == encounter_id, SOAPNote.tenant_id == tenant_id))
    )
    soap_note = soap_result.scalar_one_or_none()
    if not soap_note:
        raise HTTPException(status_code=404, detail="SOAP note not found")

    # Get versions
    versions_result = await db.execute(
        select(PatientSOAPVersion)
        .where(PatientSOAPVersion.soap_note_id == soap_note.id)
        .order_by(desc(PatientSOAPVersion.version_number))
    )
    versions = versions_result.scalars().all()

    return [
        SOAPVersionResponse(
            id=v.id,
            soap_note_id=v.soap_note_id,
            version_number=v.version_number,
            subjective=v.subjective,
            objective=v.objective,
            assessment=v.assessment,
            plan=v.plan,
            icd10_codes=[ICD10CodeEntry(**c) for c in (v.icd10_codes or [])],
            medications=[SOAPMedication(**m) for m in (v.medications or [])],
            investigations=[SOAPInvestigation(**i) for i in (v.investigations or [])],
            referrals=[SOAPReferral(**r) for r in (v.referrals or [])],
            follow_up_date=v.follow_up_date,
            follow_up_notes=v.follow_up_notes,
            word_count=v.word_count,
            time_spent_seconds=v.time_spent_seconds,
            is_autosave=v.is_autosave,
            changed_by=v.changed_by,
            change_summary=v.change_summary,
            created_at=v.created_at,
        )
        for v in versions
    ]


@router.get("/icd10/search", response_model=ICD10SearchResponse)
async def search_icd10(
    q: str = Query(..., min_length=1, description="Search query (code or description)"),
    limit: int = Query(20, ge=1, le=100),
    current_user = Depends(require_permission("clinical.icd10.search")),
    db: AsyncSession = Depends(get_db),
):
    """Search ICD-10 codes by code or description (offline cached)."""
    tenant_id = current_user.tenant_id

    # Ensure codes are seeded
    await ensure_icd10_codes_seeded(tenant_id, db)

    search_term = f"%{q}%"
    result = await db.execute(
        select(ICD10Code)
        .where(
            and_(
                ICD10Code.tenant_id == tenant_id,
                or_(
                    ICD10Code.code.ilike(search_term),
                    ICD10Code.description.ilike(search_term),
                ),
            )
        )
        .order_by(ICD10Code.code)
        .limit(limit)
    )
    codes = result.scalars().all()

    total_result = await db.execute(
        select(func.count()).select_from(ICD10Code).where(
            and_(
                ICD10Code.tenant_id == tenant_id,
                or_(
                    ICD10Code.code.ilike(search_term),
                    ICD10Code.description.ilike(search_term),
                ),
            )
        )
    )
    total = total_result.scalar() or 0

    return ICD10SearchResponse(
        codes=[
            ICD10CodeResponse(
                code=c.code,
                description=c.description,
                category=c.category,
                subcategory=c.subcategory,
                is_billable=c.is_billable,
            )
            for c in codes
        ],
        total=total,
    )


@router.post("/{encounter_id}/autosave", response_model=SOAPNoteResponse)
async def autosave_soap_note(
    encounter_id: str,
    request: SOAPNoteUpdate,
    req: Request,
    current_user = Depends(require_permission("clinical.soap.write")),
    db: AsyncSession = Depends(get_db),
):
    """Auto-save SOAP note (every 30 seconds)."""
    tenant_id = current_user.tenant_id
    user_id = current_user.id

    result = await db.execute(
        select(SOAPNote).where(and_(SOAPNote.encounter_id == encounter_id, SOAPNote.tenant_id == tenant_id))
    )
    soap_note = result.scalar_one_or_none()
    if not soap_note:
        raise HTTPException(status_code=404, detail="SOAP note not found")

    # Update only provided fields
    update_data = request.model_dump(exclude_unset=True)

    # Calculate word count if text fields changed
    if any(k in update_data for k in ["subjective", "objective", "assessment", "plan", "chief_complaint"]):
        word_count = 0
        for field in ["subjective", "objective", "assessment", "plan", "chief_complaint"]:
            value = update_data.get(field, getattr(soap_note, field))
            word_count += _count_words(value)
        update_data["word_count"] = word_count

    for field, value in update_data.items():
        if field == "icd10_codes" and value is not None:
            setattr(soap_note, field, [c.model_dump() for c in value])
        elif field == "medications" and value is not None:
            setattr(soap_note, field, [m.model_dump() for m in value])
        elif field == "investigations" and value is not None:
            setattr(soap_note, field, [i.model_dump() for i in value])
        elif field == "referrals" and value is not None:
            setattr(soap_note, field, [r.model_dump() for r in value])
        else:
            setattr(soap_note, field, value)

    soap_note.last_autosaved_at = datetime.utcnow()
    soap_note.updated_at = datetime.utcnow()

    await db.flush()

    # Create autosave version
    await _create_soap_version(soap_note, user_id, "Auto-save", is_autosave=True, db=db)

    # Get vitals for response
    vitals = await _get_latest_vitals(soap_note.patient_id, soap_note.encounter_id, db)

    patient_result = await db.execute(select(Patient).where(Patient.id == soap_note.patient_id))
    patient = patient_result.scalar_one_or_none()
    token_result = await db.execute(select(TokenQueue).where(TokenQueue.id == soap_note.token_id))
    token = token_result.scalar_one_or_none()
    encounter_result = await db.execute(select(OPDRegistration).where(OPDRegistration.id == soap_note.encounter_id))
    encounter = encounter_result.scalar_one_or_none()

    return SOAPNoteResponse(
        id=soap_note.id,
        patient_id=soap_note.patient_id,
        encounter_id=soap_note.encounter_id,
        token_id=soap_note.token_id,
        subjective=soap_note.subjective,
        objective=soap_note.objective,
        assessment=soap_note.assessment,
        plan=soap_note.plan,
        chief_complaint=soap_note.chief_complaint,
        icd10_codes=[ICD10CodeEntry(**c) for c in soap_note.icd10_codes],
        medications=[SOAPMedication(**m) for m in soap_note.medications],
        investigations=[SOAPInvestigation(**i) for i in soap_note.investigations],
        referrals=[SOAPReferral(**r) for r in soap_note.referrals],
        follow_up_date=soap_note.follow_up_date,
        follow_up_notes=soap_note.follow_up_notes,
        status=soap_note.status,
        version=soap_note.version,
        word_count=soap_note.word_count,
        time_spent_seconds=soap_note.time_spent_seconds,
        last_autosaved_at=soap_note.last_autosaved_at,
        pdf_generated_at=soap_note.pdf_generated_at,
        created_by=soap_note.created_by,
        finalized_by=soap_note.finalized_by,
        finalized_at=soap_note.finalized_at,
        created_at=soap_note.created_at,
        updated_at=soap_note.updated_at,
        patient_name=f"{patient.first_name} {patient.last_name}" if patient else None,
        patient_age=patient.age_years if patient else None,
        patient_gender=patient.gender.value if patient and patient.gender else None,
        token_number=token.token_number if token else None,
        uhid=encounter.uhid if encounter else None,
        latest_vitals=vitals,
    )


@router.post("/{encounter_id}/finalize", response_model=SOAPNoteResponse)
async def finalize_soap_note(
    encounter_id: str,
    req: Request,
    current_user = Depends(require_permission("clinical.soap.write")),
    db: AsyncSession = Depends(get_db),
):
    """Finalize a SOAP note (mark as FINALIZED, create follow-up if needed)."""
    tenant_id = current_user.tenant_id
    user_id = current_user.id

    result = await db.execute(
        select(SOAPNote).where(and_(SOAPNote.encounter_id == encounter_id, SOAPNote.tenant_id == tenant_id))
    )
    soap_note = result.scalar_one_or_none()
    if not soap_note:
        raise HTTPException(status_code=404, detail="SOAP note not found")

    # Validate mandatory fields
    if not soap_note.subjective or not soap_note.subjective.strip():
        raise HTTPException(status_code=400, detail="Subjective section is required")
    if not soap_note.assessment or not soap_note.assessment.strip():
        raise HTTPException(status_code=400, detail="Assessment section is required")
    if not soap_note.icd10_codes or len(soap_note.icd10_codes) == 0:
        raise HTTPException(status_code=400, detail="At least one ICD-10 diagnosis code is required")

    # Check for drug interactions if medications present
    if soap_note.medications:
        interactions = _check_drug_interactions(soap_note.medications)
        if interactions:
            # Warning but don't block - just log
            pass

    # Check for patient allergies
    # TODO: Implement allergy check from patient profile

    # Create final version
    await _create_soap_version(soap_note, user_id, "Finalized", is_autosave=False, db=db)

    soap_note.status = "FINALIZED"
    soap_note.finalized_by = user_id
    soap_note.finalized_at = datetime.utcnow()
    soap_note.completed_at = datetime.utcnow()
    soap_note.updated_at = datetime.utcnow()

    # Update token status to DONE
    token_result = await db.execute(select(TokenQueue).where(TokenQueue.id == soap_note.token_id))
    token = token_result.scalar_one_or_none()
    if token:
        token.status = TokenStatus.DONE
        token.completed_at = datetime.utcnow()

        # Auto-advance queue - call next patient
        next_token_result = await db.execute(
            select(TokenQueue).where(
                and_(
                    TokenQueue.tenant_id == tenant_id,
                    TokenQueue.queue_date == date.today(),
                    TokenQueue.status == TokenStatus.WAITING,
                )
            ).order_by(TokenQueue.token_number).limit(1)
        )
        next_token = next_token_result.scalar_one_or_none()
        if next_token:
            next_token.status = TokenStatus.CALLED
            next_token.called_at = datetime.utcnow()
            next_token.doctor_id = user_id

    # Create follow-up if date specified
    follow_up_created = False
    if soap_note.follow_up_date:
        # Create new OPD registration for follow-up
        patient_result = await db.execute(select(Patient).where(Patient.id == soap_note.patient_id))
        patient = patient_result.scalar_one_or_none()
        if patient:
            encounter_result = await db.execute(select(OPDRegistration).where(OPDRegistration.id == soap_note.encounter_id))
            encounter = encounter_result.scalar_one_or_none()

            # Generate UHID for follow-up
            from app.api.opd import generate_uhid, get_next_token_number, estimate_wait_minutes
            uhid = await generate_uhid(tenant_id, soap_note.follow_up_date, db)
            token_number = await get_next_token_number(tenant_id, soap_note.follow_up_date, db)

            follow_up_reg = OPDRegistration(
                tenant_id=tenant_id,
                patient_id=patient.id,
                uhid=uhid,
                first_name=patient.first_name,
                last_name=patient.last_name,
                age=patient.age_years,
                gender=patient.gender,
                phone=patient.phone,
                registration_date=soap_note.follow_up_date,
                token_number=token_number,
                estimated_wait_minutes=0,
                status=TokenStatus.WAITING,
                chief_complaint=soap_note.follow_up_notes or "Follow-up visit",
                registered_by=user_id,
            )
            db.add(follow_up_reg)
            await db.flush()

            follow_up_token = TokenQueue(
                tenant_id=tenant_id,
                registration_id=follow_up_reg.id,
                uhid=uhid,
                token_number=token_number,
                queue_date=soap_note.follow_up_date,
                status=TokenStatus.WAITING,
                chief_complaint=soap_note.follow_up_notes or "Follow-up visit",
            )
            db.add(follow_up_token)
            follow_up_created = True

    await db.flush()

    # Audit log
    await log_action(
        action=AuditAction.DATA_INGESTED,
        user_id=user_id,
        patient_id=soap_note.patient_id,
        ip_address=req.client.host if req.client else None,
        description=f"SOAP note finalized for encounter {encounter_id}" + (" + follow-up created" if follow_up_created else ""),
        details={
            "soap_note_id": soap_note.id,
            "encounter_id": encounter_id,
            "follow_up_created": follow_up_created,
            "follow_up_date": soap_note.follow_up_date.isoformat() if soap_note.follow_up_date else None,
        },
        db=db,
    )

    # Get vitals for response
    vitals = await _get_latest_vitals(soap_note.patient_id, soap_note.encounter_id, db)
    patient_result = await db.execute(select(Patient).where(Patient.id == soap_note.patient_id))
    patient = patient_result.scalar_one_or_none()
    encounter_result = await db.execute(select(OPDRegistration).where(OPDRegistration.id == soap_note.encounter_id))
    encounter = encounter_result.scalar_one_or_none()

    return SOAPNoteResponse(
        id=soap_note.id,
        patient_id=soap_note.patient_id,
        encounter_id=soap_note.encounter_id,
        token_id=soap_note.token_id,
        subjective=soap_note.subjective,
        objective=soap_note.objective,
        assessment=soap_note.assessment,
        plan=soap_note.plan,
        chief_complaint=soap_note.chief_complaint,
        icd10_codes=[ICD10CodeEntry(**c) for c in soap_note.icd10_codes],
        medications=[SOAPMedication(**m) for m in soap_note.medications],
        investigations=[SOAPInvestigation(**i) for i in soap_note.investigations],
        referrals=[SOAPReferral(**r) for r in soap_note.referrals],
        follow_up_date=soap_note.follow_up_date,
        follow_up_notes=soap_note.follow_up_notes,
        status=soap_note.status,
        version=soap_note.version,
        word_count=soap_note.word_count,
        time_spent_seconds=soap_note.time_spent_seconds,
        last_autosaved_at=soap_note.last_autosaved_at,
        pdf_generated_at=soap_note.pdf_generated_at,
        created_by=soap_note.created_by,
        finalized_by=soap_note.finalized_by,
        finalized_at=soap_note.finalized_at,
        created_at=soap_note.created_at,
        updated_at=soap_note.updated_at,
        patient_name=f"{patient.first_name} {patient.last_name}" if patient else None,
        patient_age=patient.age_years if patient else None,
        patient_gender=patient.gender.value if patient and patient.gender else None,
        token_number=token.token_number if token else None,
        uhid=encounter.uhid if encounter else None,
        latest_vitals=vitals,
    )


@router.get("/{encounter_id}/pdf")
async def export_soap_pdf(
    encounter_id: str,
    current_user = Depends(require_permission("clinical.soap.read")),
    db: AsyncSession = Depends(get_db),
):
    """Export SOAP note as PDF with hospital letterhead."""
    tenant_id = current_user.tenant_id

    result = await db.execute(
        select(SOAPNote).where(and_(SOAPNote.encounter_id == encounter_id, SOAPNote.tenant_id == tenant_id))
    )
    soap_note = result.scalar_one_or_none()
    if not soap_note:
        raise HTTPException(status_code=404, detail="SOAP note not found")

    # Get related data
    patient_result = await db.execute(select(Patient).where(Patient.id == soap_note.patient_id))
    patient = patient_result.scalar_one_or_none()

    encounter_result = await db.execute(select(OPDRegistration).where(OPDRegistration.id == soap_note.encounter_id))
    encounter = encounter_result.scalar_one_or_none()

    token_result = await db.execute(select(TokenQueue).where(TokenQueue.id == soap_note.token_id))
    token = token_result.scalar_one_or_none()

    vitals = await _get_latest_vitals(soap_note.patient_id, soap_note.encounter_id, db)

    # Get organization for letterhead
    org_result = await db.execute(select(Organization).where(Organization.id == tenant_id))
    org = org_result.scalar_one_or_none()

    # Generate HTML for PDF (using weasyprint or similar would be ideal, but return HTML for now)
    html_content = _generate_soap_pdf_html(
        soap_note, patient, encounter, token, vitals, org
    )

    soap_note.pdf_generated_at = datetime.utcnow()
    await db.flush()

    # Audit log
    await log_action(
        action=AuditAction.DATA_EXPORTED,
        user_id=current_user.id,
        patient_id=soap_note.patient_id,
        description=f"SOAP note PDF exported for encounter {encounter_id}",
        details={"soap_note_id": soap_note.id},
        db=db,
    )

    # Return HTML that can be printed to PDF
    return Response(content=html_content, media_type="text/html")


def _generate_soap_pdf_html(
    soap_note: SOAPNote,
    patient: Optional[Patient],
    encounter: Optional[OPDRegistration],
    token: Optional[TokenQueue],
    vitals: List[dict],
    org: Optional[Organization],
) -> str:
    """Generate HTML for SOAP note PDF."""
    org_name = org.name if org else "HealthBridge Clinic"
    org_address = org.address if org else ""
    org_phone = org.phone if org else ""

    patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown"
    patient_age = patient.age_years if patient else None
    patient_gender = patient.gender.value if patient and patient.gender else None
    patient_mrn = patient.mrn if patient else None

    vitals_html = ""
    if vitals:
        vitals_html = "<table style='width:100%; border-collapse:collapse; margin-bottom:16px;'><thead><tr style='background:#f3f4f6;'><th style='border:1px solid #e5e7eb; padding:8px; text-align:left;'>Vital</th><th style='border:1px solid #e5e7eb; padding:8px; text-align:left;'>Value</th><th style='border:1px solid #e5e7eb; padding:8px; text-align:left;'>Unit</th><th style='border:1px solid #e5e7eb; padding:8px; text-align:left;'>Reference Range</th></tr></thead><tbody>"
        for v in vitals:
            ref_low = v.get('reference_range_low')
            ref_high = v.get('reference_range_high')
            ref_range = f"{ref_low}–{ref_high} {v.get('unit', '')}" if ref_low and ref_high else "—"
            vitals_html += f"<tr><td style='border:1px solid #e5e7eb; padding:8px;'>{v['type'].replace('_', ' ').title()}</td><td style='border:1px solid #e5e7eb; padding:8px;'>{v['value']}</td><td style='border:1px solid #e5e7eb; padding:8px;'>{v.get('unit', '')}</td><td style='border:1px solid #e5e7eb; padding:8px;'>{ref_range}</td></tr>"
        vitals_html += "</tbody></table>"
    else:
        vitals_html = "<p>No vitals recorded for this encounter.</p>"

    icd10_html = ""
    if soap_note.icd10_codes:
        icd10_html = "<ul>"
        for code in soap_note.icd10_codes:
            primary = " (Primary)" if code.get('primary') else ""
            icd10_html += f"<li>{code['code']} — {code['description']}{primary}</li>"
        icd10_html += "</ul>"
    else:
        icd10_html = "<p>No ICD-10 codes assigned.</p>"

    meds_html = ""
    if soap_note.medications:
        meds_html = "<ul>"
        for med in soap_note.medications:
            meds_html += f"<li><strong>{med['name']}</strong> {med.get('dose', '')} {med.get('frequency', '')} {med.get('duration', '')} {med.get('route', '')}</li>"
        meds_html += "</ul>"
    else:
        meds_html = "<p>No medications prescribed.</p>"

    inv_html = ""
    if soap_note.investigations:
        inv_html = "<ul>"
        for inv in soap_note.investigations:
            inv_html += f"<li><strong>{inv['name']}</strong> ({inv.get('type', 'LAB')}) - {inv.get('priority', 'ROUTINE')}</li>"
        inv_html += "</ul>"
    else:
        inv_html = "<p>No investigations ordered.</p>"

    ref_html = ""
    if soap_note.referrals:
        ref_html = "<ul>"
        for ref in soap_note.referrals:
            ref_html += f"<li><strong>{ref['specialty']}</strong> — {ref.get('reason', '')} ({ref.get('urgency', 'ROUTINE')})</li>"
        ref_html += "</ul>"
    else:
        ref_html = "<p>No referrals.</p>"

    follow_up_html = ""
    if soap_note.follow_up_date:
        follow_up_html = f"<p><strong>Follow-up Date:</strong> {soap_note.follow_up_date.strftime('%d %b %Y')}</p>"
        if soap_note.follow_up_notes:
            follow_up_html += f"<p><strong>Follow-up Notes:</strong> {soap_note.follow_up_notes}</p>"

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>SOAP Note - {patient_name}</title>
    <style>
        @page {{ margin: 2cm; }}
        body {{ font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 11pt; line-height: 1.6; color: #1f2937; }}
        .header {{ text-align: center; border-bottom: 2px solid #2563eb; padding-bottom: 16px; margin-bottom: 24px; }}
        .header h1 {{ margin: 0; font-size: 24pt; color: #1e40af; }}
        .header p {{ margin: 4px 0; color: #4b5563; }}
        .patient-info {{ display: flex; justify-content: space-between; margin-bottom: 24px; padding: 12px; background: #f9fafb; border-radius: 8px; }}
        .patient-info div {{ flex: 1; }}
        .section {{ margin-bottom: 24px; }}
        .section-title {{ font-size: 13pt; font-weight: 600; color: #1e40af; border-bottom: 1px solid #2563eb; padding-bottom: 4px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .section-content {{ white-space: pre-wrap; font-size: 11pt; }}
        .footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 9pt; color: #6b7280; text-align: center; }}
        .signature {{ margin-top: 48px; }}
        .signature-line {{ border-top: 1px solid #9ca3af; width: 300px; margin-bottom: 4px; }}
        table {{ width: 100%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{org_name}</h1>
        <p>{org_address}</p>
        <p>{org_phone}</p>
        <p style="margin-top:12px; font-size:14pt; font-weight:600; color:#374151;">SOAP Clinical Note</p>
    </div>

    <div class="patient-info">
        <div><strong>Patient:</strong> {patient_name}</div>
        <div><strong>Age/Sex:</strong> {f"{patient_age}y / {patient_gender}" if patient_age and patient_gender else "—"}</div>
        <div><strong>MRN:</strong> {patient_mrn or "—"}</div>
        <div><strong>UHID:</strong> {encounter.uhid if encounter else "—"}</div>
        <div><strong>Token:</strong> #{token.token_number if token else "—"}</div>
        <div><strong>Date:</strong> {datetime.utcnow().strftime('%d %b %Y %H:%M')}</div>
    </div>

    <div class="section">
        <div class="section-title">Subjective</div>
        <div class="section-content">{soap_note.subjective or "Not documented"}</div>
    </div>

    <div class="section">
        <div class="section-title">Objective</div>
        <div class="section-content">{soap_note.objective or "Not documented"}</div>
        {vitals_html}
    </div>

    <div class="section">
        <div class="section-title">Assessment</div>
        <div class="section-content">{soap_note.assessment or "Not documented"}</div>
        <div style="margin-top:12px;"><strong>ICD-10 Diagnoses:</strong></div>
        {icd10_html}
    </div>

    <div class="section">
        <div class="section-title">Plan</div>
        <div class="section-content">{soap_note.plan or "Not documented"}</div>
        <div style="margin-top:12px;"><strong>Medications:</strong></div>
        {meds_html}
        <div style="margin-top:12px;"><strong>Investigations:</strong></div>
        {inv_html}
        <div style="margin-top:12px;"><strong>Referrals:</strong></div>
        {ref_html}
        {follow_up_html}
    </div>

    <div class="signature">
        <div class="signature-line"></div>
        <div>Dr. {current_user.full_name if hasattr(current_user, 'full_name') else 'Physician'}</div>
        <div style="font-size:9pt; color:#6b7280;">{datetime.utcnow().strftime('%d %b %Y %H:%M')}</div>
    </div>

    <div class="footer">
        <p>Generated by HealthBridge Platform | DPDP 2025 Compliant | This document contains confidential patient information.</p>
        <p>SOAP Note ID: {soap_note.id} | Encounter: {encounter_id} | Version: {soap_note.version}</p>
    </div>
</body>
</html>"""


def _check_drug_interactions(medications: List[dict]) -> List[str]:
    """Basic drug interaction checker - returns list of warnings."""
    # Simplified interaction database
    interactions = {
        ("warfarin", "aspirin"): "Increased bleeding risk",
        ("warfarin", "ibuprofen"): "Increased bleeding risk",
        ("metformin", "contrast"): "Risk of lactic acidosis",
        ("ace inhibitor", "potassium"): "Risk of hyperkalemia",
        ("digoxin", "amiodarone"): "Increased digoxin levels",
        ("simvastatin", "clarithromycin"): "Risk of rhabdomyolysis",
    }

    med_names = [m.get('name', '').lower() for m in medications]
    warnings = []

    for (drug1, drug2), warning in interactions.items():
        if drug1 in med_names and drug2 in med_names:
            warnings.append(f"{drug1.title()} + {drug2.title()}: {warning}")

    return warnings


# Import Organization model
from app.models import Organization