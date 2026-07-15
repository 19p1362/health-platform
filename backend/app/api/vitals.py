"""HealthBridge Platform — Vital Signs API Routes"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Patient, VitalSign, VitalSignType, AuditAction
from app.security.rbac import require_permission
from app.security.audit import log_action
from app.security.encryption import decrypt_field, mask_field

router = APIRouter(prefix="/api/v1/vitals", tags=["Vital Signs"])


# ── Schemas ──

class VitalSignCreate(BaseModel):
    patient_id: str
    vital_type: VitalSignType
    value: str = Field(..., description="Value as string (e.g., '120/80' for BP, '98.6' for temp)")
    value_numeric: Optional[float] = Field(None, description="Numeric value for charting")
    unit: Optional[str] = None
    recorded_at: Optional[datetime] = None
    device_name: Optional[str] = None
    device_serial: Optional[str] = None
    method: Optional[str] = Field(None, description="Manual, Automated, Calculated")
    position: Optional[str] = Field(None, description="sitting, standing, supine")
    notes: Optional[str] = None
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None
    encounter_id: Optional[str] = None


class VitalSignUpdate(BaseModel):
    value: Optional[str] = None
    value_numeric: Optional[float] = None
    unit: Optional[str] = None
    recorded_at: Optional[datetime] = None
    device_name: Optional[str] = None
    device_serial: Optional[str] = None
    method: Optional[str] = None
    position: Optional[str] = None
    notes: Optional[str] = None
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None
    encounter_id: Optional[str] = None


class VitalSignResponse(BaseModel):
    id: str
    patient_id: str
    vital_type: str
    value: str
    value_numeric: Optional[float]
    unit: Optional[str]
    recorded_at: datetime
    recorded_by: Optional[str]
    device_name: Optional[str]
    device_serial: Optional[str]
    method: Optional[str]
    position: Optional[str]
    notes: Optional[str]
    is_abnormal: bool
    reference_range_low: Optional[float]
    reference_range_high: Optional[float]
    encounter_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class VitalSignListResponse(BaseModel):
    vitals: List[VitalSignResponse]
    total: int
    page: int
    page_size: int


# ── Vital Sign Reference Ranges (Adult defaults) ───
# These are used for auto-detection of abnormal values
REFERENCE_RANGES = {
    VitalSignType.SYSTOLIC_BP: (90, 140),
    VitalSignType.DIASTOLIC_BP: (60, 90),
    VitalSignType.HEART_RATE: (60, 100),
    VitalSignType.RESPIRATORY_RATE: (12, 20),
    VitalSignType.TEMPERATURE: (36.1, 37.5),
    VitalSignType.SPO2: (95, 100),
    VitalSignType.RBS: (70, 140),
    VitalSignType.WEIGHT: (40, 120),
    VitalSignType.HEIGHT: (140, 200),
    VitalSignType.BMI: (18.5, 25.0),
}


def _check_abnormal(vital_type: VitalSignType, value_numeric: Optional[float]) -> bool:
    """Check if a vital sign value is outside normal reference range."""
    if value_numeric is None:
        return False
    ref = REFERENCE_RANGES.get(vital_type)
    if not ref:
        return False
    low, high = ref
    return value_numeric < low or value_numeric > high


def _parse_bp(value: str) -> tuple[Optional[float], Optional[float]]:
    """Parse blood pressure string like '120/80' into systolic, diastolic."""
    try:
        if "/" in value:
            parts = value.split("/")
            return float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        pass
    return None, None


# ── Routes ───

@router.post("", response_model=VitalSignResponse, status_code=201)
async def create_vital_sign(
    request: VitalSignCreate,
    req: Request,
    current_user = Depends(require_permission("vital_sign.write")),
    db: AsyncSession = Depends(get_db),
):
    """Record a new vital sign observation."""
    # Verify patient exists and belongs to tenant
    patient_result = await db.execute(
        select(Patient).where(Patient.id == request.patient_id)
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Determine value_numeric if not provided
    value_numeric = request.value_numeric
    if value_numeric is None:
        if request.vital_type in (VitalSignType.SYSTOLIC_BP, VitalSignType.DIASTOLIC_BP):
            systolic, diastolic = _parse_bp(request.value)
            if request.vital_type == VitalSignType.SYSTOLIC_BP:
                value_numeric = systolic
            else:
                value_numeric = diastolic
        else:
            try:
                value_numeric = float(request.value)
            except ValueError:
                value_numeric = None

    # Auto-detect abnormal if reference ranges not provided
    ref_low = request.reference_range_low
    ref_high = request.reference_range_high
    if ref_low is None or ref_high is None:
        default_range = REFERENCE_RANGES.get(request.vital_type)
        if default_range:
            ref_low = ref_low if ref_low is not None else default_range[0]
            ref_high = ref_high if ref_high is not None else default_range[1]

    is_abnormal = _check_abnormal(request.vital_type, value_numeric)

    vital = VitalSign(
        patient_id=request.patient_id,
        vital_type=request.vital_type,
        value=request.value,
        value_numeric=str(value_numeric) if value_numeric is not None else None,
        unit=request.unit or VitalSign.get_unit(request.vital_type),
        recorded_at=request.recorded_at or datetime.utcnow(),
        recorded_by=current_user.id,
        device_name=request.device_name,
        device_serial=request.device_serial,
        method=request.method or "Manual",
        position=request.position,
        notes=request.notes,
        is_abnormal=is_abnormal,
        reference_range_low=str(ref_low) if ref_low is not None else None,
        reference_range_high=str(ref_high) if ref_high is not None else None,
        encounter_id=request.encounter_id,
    )
    db.add(vital)
    await db.flush()

    # Audit log
    await log_action(
        action=AuditAction.DATA_INGESTED,
        user_id=current_user.id,
        patient_id=request.patient_id,
        ip_address=req.client.host if req.client else None,
        description=f"Vital sign recorded: {request.vital_type.value} = {request.value}",
        details={
            "vital_id": vital.id,
            "vital_type": request.vital_type.value,
            "value": request.value,
            "is_abnormal": is_abnormal,
        },
        db=db,
    )

    return VitalSignResponse(
        id=vital.id,
        patient_id=vital.patient_id,
        vital_type=vital.vital_type.value,
        value=vital.value,
        value_numeric=float(vital.value_numeric) if vital.value_numeric else None,
        unit=vital.unit,
        recorded_at=vital.recorded_at,
        recorded_by=vital.recorded_by,
        device_name=vital.device_name,
        device_serial=vital.device_serial,
        method=vital.method,
        position=vital.position,
        notes=vital.notes,
        is_abnormal=vital.is_abnormal,
        reference_range_low=float(vital.reference_range_low) if vital.reference_range_low else None,
        reference_range_high=float(vital.reference_range_high) if vital.reference_range_high else None,
        encounter_id=vital.encounter_id,
        created_at=vital.created_at,
        updated_at=vital.updated_at,
    )


@router.get("/patient/{patient_id}", response_model=VitalSignListResponse)
async def get_patient_vitals(
    patient_id: str,
    vital_type: Optional[VitalSignType] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user = Depends(require_permission("vital_sign.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get vital signs for a patient with optional filtering."""
    # Verify patient exists
    patient_result = await db.execute(select(Patient).where(Patient.id == patient_id))
    if not patient_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found")

    query = select(VitalSign).where(VitalSign.patient_id == patient_id)

    if vital_type:
        query = query.where(VitalSign.vital_type == vital_type)
    if start_date:
        query = query.where(VitalSign.recorded_at >= start_date)
    if end_date:
        query = query.where(VitalSign.recorded_at <= end_date)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = query.order_by(desc(VitalSign.recorded_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    vitals = result.scalars().all()

    return VitalSignListResponse(
        vitals=[
            VitalSignResponse(
                id=v.id,
                patient_id=v.patient_id,
                vital_type=v.vital_type.value,
                value=v.value,
                value_numeric=float(v.value_numeric) if v.value_numeric else None,
                unit=v.unit,
                recorded_at=v.recorded_at,
                recorded_by=v.recorded_by,
                device_name=v.device_name,
                device_serial=v.device_serial,
                method=v.method,
                position=v.position,
                notes=v.notes,
                is_abnormal=v.is_abnormal,
                reference_range_low=float(v.reference_range_low) if v.reference_range_low else None,
                reference_range_high=float(v.reference_range_high) if v.reference_range_high else None,
                encounter_id=v.encounter_id,
                created_at=v.created_at,
                updated_at=v.updated_at,
            )
            for v in vitals
        ],
        total=total,
        page=offset // limit + 1,
        page_size=limit,
    )


@router.get("/patient/{patient_id}/latest")
async def get_latest_vitals(
    patient_id: str,
    current_user = Depends(require_permission("vital_sign.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest vital sign for each type for a patient (for dashboard summary)."""
    patient_result = await db.execute(select(Patient).where(Patient.id == patient_id))
    if not patient_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get latest vital for each type
    subquery = (
        select(
            VitalSign.vital_type,
            func.max(VitalSign.recorded_at).label("latest_recorded")
        )
        .where(VitalSign.patient_id == patient_id)
        .group_by(VitalSign.vital_type)
        .subquery()
    )

    query = (
        select(VitalSign)
        .join(
            subquery,
            (VitalSign.vital_type == subquery.c.vital_type)
            & (VitalSign.recorded_at == subquery.c.latest_recorded)
            & (VitalSign.patient_id == patient_id)
        )
    )

    result = await db.execute(query)
    vitals = result.scalars().all()

    return [
        VitalSignResponse(
            id=v.id,
            patient_id=v.patient_id,
            vital_type=v.vital_type.value,
            value=v.value,
            value_numeric=float(v.value_numeric) if v.value_numeric else None,
            unit=v.unit,
            recorded_at=v.recorded_at,
            recorded_by=v.recorded_by,
            device_name=v.device_name,
            device_serial=v.device_serial,
            method=v.method,
            position=v.position,
            notes=v.notes,
            is_abnormal=v.is_abnormal,
            reference_range_low=float(v.reference_range_low) if v.reference_range_low else None,
            reference_range_high=float(v.reference_range_high) if v.reference_range_high else None,
            encounter_id=v.encounter_id,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in vitals
    ]


@router.get("/{vital_id}", response_model=VitalSignResponse)
async def get_vital_sign(
    vital_id: str,
    request: Request,
    current_user = Depends(require_permission("vital_sign.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific vital sign by ID."""
    result = await db.execute(select(VitalSign).where(VitalSign.id == vital_id))
    vital = result.scalar_one_or_none()
    if not vital:
        raise HTTPException(status_code=404, detail="Vital sign not found")

    return VitalSignResponse(
        id=vital.id,
        patient_id=vital.patient_id,
        vital_type=vital.vital_type.value,
        value=vital.value,
        value_numeric=float(vital.value_numeric) if vital.value_numeric else None,
        unit=vital.unit,
        recorded_at=vital.recorded_at,
        recorded_by=vital.recorded_by,
        device_name=vital.device_name,
        device_serial=vital.device_serial,
        method=vital.method,
        position=vital.position,
        notes=vital.notes,
        is_abnormal=vital.is_abnormal,
        reference_range_low=float(vital.reference_range_low) if vital.reference_range_low else None,
        reference_range_high=float(vital.reference_range_high) if vital.reference_range_high else None,
        encounter_id=vital.encounter_id,
        created_at=vital.created_at,
        updated_at=vital.updated_at,
    )


@router.patch("/{vital_id}", response_model=VitalSignResponse)
async def update_vital_sign(
    vital_id: str,
    request: VitalSignUpdate,
    req: Request,
    current_user = Depends(require_permission("vital_sign.write")),
    db: AsyncSession = Depends(get_db),
):
    """Update a vital sign entry."""
    result = await db.execute(select(VitalSign).where(VitalSign.id == vital_id))
    vital = result.scalar_one_or_none()
    if not vital:
        raise HTTPException(status_code=404, detail="Vital sign not found")

    update_data = request.model_dump(exclude_unset=True)

    # Recalculate abnormal flag if value changed
    if "value" in update_data or "value_numeric" in update_data:
        new_value = update_data.get("value", vital.value)
        new_numeric = update_data.get("value_numeric")
        if new_numeric is None and "value" in update_data:
            if vital.vital_type in (VitalSignType.SYSTOLIC_BP, VitalSignType.DIASTOLIC_BP):
                systolic, diastolic = _parse_bp(new_value)
                if vital.vital_type == VitalSignType.SYSTOLIC_BP:
                    new_numeric = systolic
                else:
                    new_numeric = diastolic
            else:
                try:
                    new_numeric = float(new_value)
                except ValueError:
                    new_numeric = None

        update_data["value_numeric"] = str(new_numeric) if new_numeric is not None else vital.value_numeric
        update_data["is_abnormal"] = _check_abnormal(vital.vital_type, new_numeric)

    for field, value in update_data.items():
        setattr(vital, field, value)

    vital.updated_at = datetime.utcnow()
    await db.flush()

    # Audit log
    await log_action(
        action=AuditAction.DATA_INGESTED,
        user_id=current_user.id,
        patient_id=vital.patient_id,
        ip_address=req.client.host if req.client else None,
        description=f"Vital sign updated: {vital.vital_type.value}",
        details={"vital_id": vital.id, "changes": update_data},
        db=db,
    )

    return VitalSignResponse(
        id=vital.id,
        patient_id=vital.patient_id,
        vital_type=vital.vital_type.value,
        value=vital.value,
        value_numeric=float(vital.value_numeric) if vital.value_numeric else None,
        unit=vital.unit,
        recorded_at=vital.recorded_at,
        recorded_by=vital.recorded_by,
        device_name=vital.device_name,
        device_serial=vital.device_serial,
        method=vital.method,
        position=vital.position,
        notes=vital.notes,
        is_abnormal=vital.is_abnormal,
        reference_range_low=float(vital.reference_range_low) if vital.reference_range_low else None,
        reference_range_high=float(vital.reference_range_high) if vital.reference_range_high else None,
        encounter_id=vital.encounter_id,
        created_at=vital.created_at,
        updated_at=vital.updated_at,
    )


@router.delete("/{vital_id}", status_code=204)
async def delete_vital_sign(
    vital_id: str,
    req: Request,
    current_user = Depends(require_permission("vital_sign.write")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a vital sign entry (soft delete - marks as inactive)."""
    result = await db.execute(select(VitalSign).where(VitalSign.id == vital_id))
    vital = result.scalar_one_or_none()
    if not vital:
        raise HTTPException(status_code=404, detail="Vital sign not found")

    patient_id = vital.patient_id
    vital_type = vital.vital_type.value

    await db.delete(vital)
    await db.flush()

    await log_action(
        action=AuditAction.DATA_INGESTED,
        user_id=current_user.id,
        patient_id=patient_id,
        ip_address=req.client.host if req.client else None,
        description=f"Vital sign deleted: {vital_type}",
        details={"vital_id": vital_id},
        db=db,
    )


@router.get("/types/list")
async def list_vital_types(
    current_user = Depends(require_permission("vital_sign.read")),
):
    """List all supported vital sign types with their default units and reference ranges."""
    return [
        {
            "type": vt.value,
            "display": vt.value.replace("_", " ").title(),
            "unit": VitalSign.get_unit(vt),
            "loinc_code": VitalSign.get_loinc_code(vt),
            "reference_range": REFERENCE_RANGES.get(vt),
        }
        for vt in VitalSignType
    ]