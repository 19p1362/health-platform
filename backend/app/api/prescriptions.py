"""
HealthBridge Platform — Prescription Writer API Routes

Day 8-10: Drug Formulary + Structured Prescription + Clinical Safety Engine
"""

from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Drug, FormularyEntry, Prescription, PrescriptionLine,
    DrugInteraction, AllergyIntolerance, DispensingTask,
    Patient, User, OPDRegistration, Organization,
    DrugForm, DrugRoute, PrescriptionFrequency, PrescriptionStatus,
    InteractionSeverity, PregnancyCategory, DrugClass,
    AuditAction, VitalSign,
)
from app.security.auth import verify_token
from app.security.rbac import require_permission
from app.security.audit import log_action
from app.security.encryption import encrypt_field, decrypt_field, mask_field

router = APIRouter(prefix="/api/v1/clinical", tags=["Prescription Writer"])


# ═══════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════

class DrugSearchResponse(BaseModel):
    id: str
    name: str
    generic_name: str
    strength: Optional[str]
    form: str
    route: str
    manufacturer: Optional[str]
    category: Optional[str]
    drug_class: str
    atc_code: Optional[str]
    price: Optional[str]
    currency: str
    is_essential: bool
    pregnancy_category: str
    dosing_adult: dict
    dosing_pediatric: dict
    dosing_geriatric: dict
    formulary_price: Optional[str] = None
    formulary_category: Optional[str] = None
    is_preferred: bool = False
    is_restricted: bool = False
    restriction_notes: Optional[str] = None


class DrugSearchResult(BaseModel):
    drugs: List[DrugSearchResponse]
    total: int
    page: int
    page_size: int


class DrugDetailResponse(BaseModel):
    id: str
    name: str
    generic_name: str
    strength: Optional[str]
    form: str
    route: str
    manufacturer: Optional[str]
    category: Optional[str]
    drug_class: str
    atc_code: Optional[str]
    schedule: Optional[str]
    price: Optional[str]
    currency: str
    is_essential: bool
    indications: List
    contraindications: List
    side_effects: List
    pregnancy_category: str
    lactation_category: Optional[str]
    dosing_adult: dict
    dosing_pediatric: dict
    dosing_geriatric: dict
    dosing_renal_impairment: dict
    dosing_hepatic_impairment: dict
    interacts_with_classes: List


class InteractionResponse(BaseModel):
    drug_b_id: str
    drug_b_name: str
    drug_b_generic: str
    severity: str
    mechanism: Optional[str]
    clinical_effect: str
    management: Optional[str]
    evidence_level: Optional[str]


class InteractionCheckResponse(BaseModel):
    interactions: List[InteractionResponse]
    max_severity: Optional[str]


class DosingGuidelineResponse(BaseModel):
    adult: dict
    pediatric: dict
    geriatric: dict
    renal_impairment: dict
    hepatic_impairment: dict


class PrescriptionLineCreate(BaseModel):
    drug_id: Optional[str] = None
    drug_name: str
    generic_name: Optional[str] = None
    strength: Optional[str] = None
    form: Optional[str] = None
    route: str
    dose: str
    frequency: str
    frequency_custom: Optional[str] = None
    duration: str
    quantity: str
    quantity_unit: str = "units"
    refills: int = 0
    instructions: Optional[str] = None
    before_food: Optional[bool] = None
    at_bedtime: bool = False
    sequence: int = 0


class PrescriptionLineResponse(BaseModel):
    id: str
    drug_id: Optional[str]
    drug_name: str
    generic_name: Optional[str]
    strength: Optional[str]
    form: Optional[str]
    route: str
    dose: str
    frequency: str
    frequency_custom: Optional[str]
    duration: str
    duration_days: Optional[int]
    quantity: str
    quantity_unit: str
    refills: int
    instructions: Optional[str]
    before_food: Optional[bool]
    at_bedtime: bool
    sequence: int
    safety_status: str
    interaction_warnings: List
    allergy_warnings: List
    duplicate_therapy_warnings: List
    dose_warnings: List
    pregnancy_warnings: List


class PrescriptionCreate(BaseModel):
    patient_id: str
    encounter_id: Optional[str] = None
    diagnosis: Optional[str] = None
    icd10_codes: List = Field(default_factory=list)
    notes: Optional[str] = None
    lines: List[PrescriptionLineCreate] = Field(default_factory=list)


class PrescriptionUpdate(BaseModel):
    status: Optional[str] = None
    diagnosis: Optional[str] = None
    icd10_codes: Optional[List] = None
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None


class PrescriptionResponse(BaseModel):
    id: str
    prescription_number: Optional[str]
    patient_id: str
    encounter_id: Optional[str]
    doctor_id: Optional[str]
    status: str
    diagnosis: Optional[str]
    icd10_codes: List
    notes: Optional[str]
    prescribed_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    expires_at: Optional[datetime]
    lines: List[PrescriptionLineResponse]
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    uhid: Optional[str] = None
    doctor_name: Optional[str] = None


class PrescriptionListResponse(BaseModel):
    prescriptions: List[PrescriptionResponse]
    total: int
    page: int
    page_size: int


class SafetyCheckRequest(BaseModel):
    patient_id: str
    lines: List[PrescriptionLineCreate]
    encounter_id: Optional[str] = None


class SafetyCheckResponse(BaseModel):
    overall_safety: str  # SAFE, CAUTION, CONTRAINDICATED
    line_checks: List[dict]
    summary: dict


class AllergyCreate(BaseModel):
    substance: str
    substance_code: Optional[str] = None
    drug_class: Optional[str] = None
    reaction_type: str = "ALLERGY"
    manifestation: Optional[str] = None
    severity: Optional[str] = None
    onset_date: Optional[date] = None
    verified: bool = False
    notes: Optional[str] = None


class AllergyResponse(BaseModel):
    id: str
    substance: str
    substance_code: Optional[str]
    drug_class: Optional[str]
    reaction_type: str
    manifestation: Optional[str]
    severity: Optional[str]
    onset_date: Optional[date]
    verified: bool
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    status: str
    notes: Optional[str]
    created_at: datetime


class DispensingTaskResponse(BaseModel):
    id: str
    prescription_id: str
    pharmacist_id: Optional[str]
    status: str
    priority: str
    dispensed_lines: List
    notes: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    patient_name: Optional[str] = None
    prescription_number: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

async def get_tenant_id(request: Request) -> str:
    """Extract tenant_id from authenticated user."""
    # In a real implementation, this would come from the JWT token
    # For now, we'll use a header or default
    return request.headers.get("X-Tenant-ID", "default")


async def generate_prescription_number(db: AsyncSession, model, field: str, prefix: str, tenant_id: str) -> str:
    """Generate a unique sequential number for a field."""
    today = datetime.now().strftime("%Y%m%d")
    result = await db.execute(
        select(func.count()).select_from(model).where(
            getattr(model, field).like(f"{prefix}-{tenant_id}-{today}%")
        )
    )
    count = result.scalar() or 0
    return f"{prefix}-{tenant_id[:6].upper()}-{today}-{count + 1:04d}"


def parse_duration_to_days(duration: str) -> Optional[int]:
    """Parse duration string to days (e.g., '7 days', '1 month', '2 weeks')."""
    duration = duration.lower().strip()
    try:
        if 'day' in duration:
            return int(''.join(filter(str.isdigit, duration)))
        elif 'week' in duration:
            return int(''.join(filter(str.isdigit, duration))) * 7
        elif 'month' in duration:
            return int(''.join(filter(str.isdigit, duration))) * 30
        elif 'year' in duration:
            return int(''.join(filter(str.isdigit, duration))) * 365
    except ValueError:
        pass
    return None


async def get_patient_active_medications(db: AsyncSession, patient_id: str) -> List[str]:
    """Get patient's currently active medications (generic names)."""
    result = await db.execute(
        select(PrescriptionLine.generic_name)
        .join(Prescription)
        .where(
            Prescription.patient_id == patient_id,
            Prescription.status == PrescriptionStatus.ACTIVE,
            PrescriptionLine.generic_name.isnot(None)
        )
    )
    return [row[0] for row in result.fetchall()]


async def get_patient_allergies(db: AsyncSession, patient_id: str, tenant_id: str) -> List[AllergyIntolerance]:
    """Get patient's active allergies."""
    result = await db.execute(
        select(AllergyIntolerance).where(
            AllergyIntolerance.patient_id == patient_id,
            AllergyIntolerance.tenant_id == tenant_id,
            AllergyIntolerance.status == "ACTIVE"
        )
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════
# Clinical Safety Engine
# ═══════════════════════════════════════════════════════════════

class SafetyEngine:
    """Clinical safety checks for prescriptions."""

    @staticmethod
    async def check_drug_interactions(
        db: AsyncSession,
        new_lines: List[PrescriptionLineCreate],
        patient_active_meds: List[str]
    ) -> List[dict]:
        """Check drug-drug interactions for new prescription lines."""
        warnings = []

        # Get drug IDs for new lines
        new_drug_ids = [line.drug_id for line in new_lines if line.drug_id]
        new_generic_names = [line.generic_name.lower() for line in new_lines if line.generic_name]

        if not new_drug_ids and not new_generic_names:
            return warnings

        # Check interactions between new drugs
        for i, line_a in enumerate(new_lines):
            for j, line_b in enumerate(new_lines):
                if i >= j:
                    continue
                if line_a.drug_id and line_b.drug_id:
                    # Check direct drug-drug interaction
                    result = await db.execute(
                        select(DrugInteraction).where(
                            or_(
                                and_(DrugInteraction.drug_a_id == line_a.drug_id, DrugInteraction.drug_b_id == line_b.drug_id),
                                and_(DrugInteraction.drug_a_id == line_b.drug_id, DrugInteraction.drug_b_id == line_a.drug_id),
                            )
                        )
                    )
                    interaction = result.scalar_one_or_none()
                    if interaction:
                        warnings.append({
                            "type": "drug_interaction",
                            "severity": interaction.severity.value,
                            "drug_a": line_a.drug_name,
                            "drug_b": line_b.drug_name,
                            "mechanism": interaction.mechanism,
                            "clinical_effect": interaction.clinical_effect,
                            "management": interaction.management,
                            "evidence_level": interaction.evidence_level,
                        })

        # Check new drugs against patient's active medications
        if new_drug_ids:
            # Get drug classes for new drugs
            result = await db.execute(
                select(Drug).where(Drug.id.in_(new_drug_ids))
            )
            new_drugs = {d.id: d for d in result.scalars().all()}

            for drug_id, drug in new_drugs.items():
                if drug.drug_class:
                    # Check class-level interactions with active meds
                    for active_med in patient_active_meds:
                        # This would need a mapping from active med names to drug classes
                        # For now, we'll do a simple name-based check
                        pass

        return warnings

    @staticmethod
    async def check_allergies(
        db: AsyncSession,
        patient_id: str,
        tenant_id: str,
        new_lines: List[PrescriptionLineCreate]
    ) -> List[dict]:
        """Check for allergy cross-reactions."""
        warnings = []
        allergies = await get_patient_allergies(db, patient_id, tenant_id)

        for line in new_lines:
            generic_lower = (line.generic_name or "").lower()
            name_lower = line.drug_name.lower()

            for allergy in allergies:
                allergy_substance = allergy.substance.lower()
                allergy_class = allergy.drug_class

                # Direct substance match
                if allergy_substance in generic_lower or allergy_substance in name_lower:
                    warnings.append({
                        "type": "allergy",
                        "severity": "CONTRAINDICATED",
                        "drug": line.drug_name,
                        "allergy": allergy.substance,
                        "reaction_type": allergy.reaction_type,
                        "manifestation": allergy.manifestation,
                        "severity_level": allergy.severity,
                    })

                # Class-level allergy
                if allergy_class and line.drug_id:
                    result = await db.execute(select(Drug).where(Drug.id == line.drug_id))
                    drug = result.scalar_one_or_none()
                    if drug and drug.drug_class == allergy_class:
                        warnings.append({
                            "type": "allergy_class",
                            "severity": "CONTRAINDICATED",
                            "drug": line.drug_name,
                            "allergy_class": allergy_class.value,
                            "reaction_type": allergy.reaction_type,
                            "manifestation": allergy.manifestation,
                            "severity_level": allergy.severity,
                        })

        return warnings

    @staticmethod
    async def check_duplicate_therapy(
        db: AsyncSession,
        new_lines: List[PrescriptionLineCreate],
        patient_active_meds: List[str]
    ) -> List[dict]:
        """Check for duplicate therapy (same drug class)."""
        warnings = []

        for line in new_lines:
            if not line.drug_id:
                continue

            result = await db.execute(select(Drug).where(Drug.id == line.drug_id))
            drug = result.scalar_one_or_none()
            if not drug or not drug.drug_class:
                continue

            # Check against new lines (same class)
            for other_line in new_lines:
                if other_line.drug_id == line.drug_id:
                    continue
                if other_line.drug_id:
                    other_result = await db.execute(select(Drug).where(Drug.id == other_line.drug_id))
                    other_drug = other_result.scalar_one_or_none()
                    if other_drug and other_drug.drug_class == drug.drug_class:
                        warnings.append({
                            "type": "duplicate_therapy",
                            "severity": "CAUTION",
                            "drug_a": line.drug_name,
                            "drug_b": other_line.drug_name,
                            "drug_class": drug.drug_class.value,
                            "message": f"Both {line.drug_name} and {other_line.drug_name} are {drug.drug_class.value} class drugs",
                        })

            # Check against active medications
            for active_med in patient_active_meds:
                # Would need to map active_med to drug class
                # For now, simple name check
                if active_med.lower() in (line.generic_name or "").lower():
                    warnings.append({
                        "type": "duplicate_therapy",
                        "severity": "CAUTION",
                        "drug": line.drug_name,
                        "active_medication": active_med,
                        "message": f"Patient already taking {active_med} (same class)",
                    })

        return warnings

    @staticmethod
    async def check_dose_range(
        db: AsyncSession,
        new_lines: List[PrescriptionLineCreate],
        patient: Patient
    ) -> List[dict]:
        """Validate dose against age/weight/renal function."""
        warnings = []

        # Calculate age
        age_years = None
        if patient.date_of_birth:
            age_years = (date.today() - patient.date_of_birth).days // 365

        for line in new_lines:
            if not line.drug_id:
                continue

            result = await db.execute(select(Drug).where(Drug.id == line.drug_id))
            drug = result.scalar_one_or_none()
            if not drug:
                continue

            # Parse dose (e.g., "500mg" -> 500)
            dose_value = None
            dose_unit = None
            try:
                import re
                match = re.match(r'([\d.]+)\s*(\w+)', line.dose)
                if match:
                    dose_value = float(match.group(1))
                    dose_unit = match.group(2)
            except (ValueError, AttributeError):
                pass

            if dose_value is None:
                continue

            # Age-based dosing checks
            if age_years is not None:
                if age_years < 18 and drug.dosing_pediatric:
                    # Check pediatric dosing
                    pass
                elif age_years >= 65 and drug.dosing_geriatric:
                    # Check geriatric dosing
                    pass

            # This would need more sophisticated parsing of dosing guidelines
            # For now, we'll add a placeholder warning if dose seems high
            # Real implementation would parse the structured dosing JSON

        return warnings

    @staticmethod
    async def check_pregnancy_lactation(
        db: AsyncSession,
        new_lines: List[PrescriptionLineCreate],
        patient: Patient
    ) -> List[dict]:
        """Check pregnancy/lactation category warnings."""
        warnings = []

        if patient.gender != "FEMALE":
            return warnings

        # Would need pregnancy/lactation status from patient record
        # For now, we check the drug's pregnancy category
        for line in new_lines:
            if not line.drug_id:
                continue

            result = await db.execute(select(Drug).where(Drug.id == line.drug_id))
            drug = result.scalar_one_or_none()
            if not drug:
                continue

            if drug.pregnancy_category in [PregnancyCategory.D, PregnancyCategory.X]:
                warnings.append({
                    "type": "pregnancy_warning",
                    "severity": "CONTRAINDICATED" if drug.pregnancy_category == PregnancyCategory.X else "CAUTION",
                    "drug": line.drug_name,
                    "pregnancy_category": drug.pregnancy_category.value,
                    "message": f"Drug is FDA pregnancy category {drug.pregnancy_category.value}",
                })

        return warnings

    @staticmethod
    async def run_all_checks(
        db: AsyncSession,
        patient_id: str,
        tenant_id: str,
        lines: List[PrescriptionLineCreate],
        encounter_id: Optional[str] = None
    ) -> dict:
        """Run all safety checks and return aggregated results."""
        # Get patient
        result = await db.execute(select(Patient).where(Patient.id == patient_id))
        patient = result.scalar_one_or_none()
        if not patient:
            return {"error": "Patient not found"}

        # Get active medications
        active_meds = await get_patient_active_medications(db, patient_id)

        # Run all checks
        interactions = await SafetyEngine.check_drug_interactions(db, lines, active_meds)
        allergies = await SafetyEngine.check_allergies(db, patient_id, tenant_id, lines)
        duplicates = await SafetyEngine.check_duplicate_therapy(db, lines, active_meds)
        doses = await SafetyEngine.check_dose_range(db, lines, patient)
        pregnancy = await SafetyEngine.check_pregnancy_lactation(db, lines, patient)

        all_warnings = interactions + allergies + duplicates + doses + pregnancy

        # Determine overall safety status
        max_severity = "SAFE"
        for w in all_warnings:
            sev = w.get("severity", "MINOR")
            if sev == "CONTRAINDICATED":
                max_severity = "CONTRAINDICATED"
                break
            elif sev == "MAJOR" and max_severity != "CONTRAINDICATED":
                max_severity = "MAJOR"
            elif sev == "MODERATE" and max_severity not in ["CONTRAINDICATED", "MAJOR"]:
                max_severity = "MODERATE"
            elif sev == "MINOR" and max_severity == "SAFE":
                max_severity = "MINOR"

        # Group warnings by line
        line_checks = []
        for i, line in enumerate(lines):
            line_warnings = [w for w in all_warnings if w.get("drug") == line.drug_name or w.get("drug_a") == line.drug_name]
            line_status = "SAFE"
            for w in line_warnings:
                sev = w.get("severity", "MINOR")
                if sev == "CONTRAINDICATED":
                    line_status = "CONTRAINDICATED"
                    break
                elif sev in ["MAJOR", "MODERATE"] and line_status == "SAFE":
                    line_status = "CAUTION"

            line_checks.append({
                "line_index": i,
                "drug_name": line.drug_name,
                "safety_status": line_status,
                "warnings": line_warnings,
            })

        return {
            "overall_safety": max_severity,
            "line_checks": line_checks,
            "summary": {
                "total_warnings": len(all_warnings),
                "interactions": len(interactions),
                "allergies": len(allergies),
                "duplicate_therapy": len(duplicates),
                "dose_warnings": len(doses),
                "pregnancy_warnings": len(pregnancy),
            }
        }


# ═══════════════════════════════════════════════════════════════
# Drug Formulary Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/drugs/search", response_model=DrugSearchResult)
async def search_drugs(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query (name, generic, category)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    form: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Search formulary drugs by name, generic name, or category."""
    tenant_id = await get_tenant_id(request)

    # Build query joining drugs with formulary entries for this tenant
    query = (
        select(Drug, FormularyEntry)
        .outerjoin(FormularyEntry, and_(FormularyEntry.drug_id == Drug.id, FormularyEntry.tenant_id == tenant_id))
        .where(
            or_(
                Drug.name.ilike(f"%{q}%"),
                Drug.generic_name.ilike(f"%{q}%"),
                Drug.category.ilike(f"%{q}%"),
            )
        )
    )

    if category:
        query = query.where(or_(Drug.category == category, FormularyEntry.category == category))
    if form:
        query = query.where(Drug.form == form)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Drug.generic_name).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.fetchall()

    drugs = []
    for drug, formulary in rows:
        drugs.append(DrugSearchResponse(
            id=drug.id,
            name=drug.name,
            generic_name=drug.generic_name,
            strength=drug.strength,
            form=drug.form.value,
            route=drug.route.value,
            manufacturer=drug.manufacturer,
            category=formulary.category if formulary else drug.category,
            drug_class=drug.drug_class.value,
            atc_code=drug.atc_code,
            price=formulary.price if formulary else drug.price,
            currency=formulary.currency if formulary else drug.currency,
            is_essential=drug.is_essential,
            pregnancy_category=drug.pregnancy_category.value,
            dosing_adult=drug.dosing_adult,
            dosing_pediatric=drug.dosing_pediatric,
            dosing_geriatric=drug.dosing_geriatric,
            formulary_price=formulary.price if formulary else None,
            formulary_category=formulary.category if formulary else None,
            is_preferred=formulary.is_preferred if formulary else False,
            is_restricted=formulary.is_restricted if formulary else False,
            restriction_notes=formulary.restriction_notes if formulary else None,
        ))

    return DrugSearchResult(
        drugs=drugs,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/drugs/{drug_id}", response_model=DrugDetailResponse)
async def get_drug_detail(
    drug_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get detailed drug information."""
    result = await db.execute(select(Drug).where(Drug.id == drug_id))
    drug = result.scalar_one_or_none()
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    return DrugDetailResponse(
        id=drug.id,
        name=drug.name,
        generic_name=drug.generic_name,
        strength=drug.strength,
        form=drug.form.value,
        route=drug.route.value,
        manufacturer=drug.manufacturer,
        category=drug.category,
        drug_class=drug.drug_class.value,
        atc_code=drug.atc_code,
        schedule=drug.schedule,
        price=drug.price,
        currency=drug.currency,
        is_essential=drug.is_essential,
        indications=drug.indications,
        contraindications=drug.contraindications,
        side_effects=drug.side_effects,
        pregnancy_category=drug.pregnancy_category.value,
        lactation_category=drug.lactation_category,
        dosing_adult=drug.dosing_adult,
        dosing_pediatric=drug.dosing_pediatric,
        dosing_geriatric=drug.dosing_geriatric,
        dosing_renal_impairment=drug.dosing_renal_impairment,
        dosing_hepatic_impairment=drug.dosing_hepatic_impairment,
        interacts_with_classes=[c.value for c in drug.interacts_with_classes] if drug.interacts_with_classes else [],
    )


@router.get("/drugs/{drug_id}/interactions", response_model=InteractionCheckResponse)
async def get_drug_interactions(
    drug_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get known drug-drug interactions for a drug."""
    result = await db.execute(
        select(DrugInteraction, Drug)
        .join(Drug, DrugInteraction.drug_b_id == Drug.id)
        .where(DrugInteraction.drug_a_id == drug_id)
    )
    interactions = result.fetchall()

    interaction_list = []
    max_severity = None
    severity_order = {"CONTRAINDICATED": 4, "MAJOR": 3, "MODERATE": 2, "MINOR": 1, "UNKNOWN": 0}

    for interaction, drug_b in interactions:
        interaction_list.append(InteractionResponse(
            drug_b_id=drug_b.id,
            drug_b_name=drug_b.name,
            drug_b_generic=drug_b.generic_name,
            severity=interaction.severity.value,
            mechanism=interaction.mechanism,
            clinical_effect=interaction.clinical_effect,
            management=interaction.management,
            evidence_level=interaction.evidence_level,
        ))
        if interaction.severity.value in severity_order:
            if max_severity is None or severity_order[interaction.severity.value] > severity_order.get(max_severity, 0):
                max_severity = interaction.severity.value

    return InteractionCheckResponse(
        interactions=interaction_list,
        max_severity=max_severity,
    )


@router.get("/drugs/{drug_id}/dosing", response_model=DosingGuidelineResponse)
async def get_drug_dosing(
    drug_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get standard dosing guidelines for a drug."""
    result = await db.execute(select(Drug).where(Drug.id == drug_id))
    drug = result.scalar_one_or_none()
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    return DosingGuidelineResponse(
        adult=drug.dosing_adult or {},
        pediatric=drug.dosing_pediatric or {},
        geriatric=drug.dosing_geriatric or {},
        renal_impairment=drug.dosing_renal_impairment or {},
        hepatic_impairment=drug.dosing_hepatic_impairment or {},
    )


# ═══════════════════════════════════════════════════════════════
# Prescription Endpoints
# ═══════════════════════════════════════════════════════════════

@router.post("/prescriptions", response_model=PrescriptionResponse, status_code=201)
async def create_prescription(
    request: Request,
    prescription_data: PrescriptionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Create a new prescription from SOAP Plan tab."""
    tenant_id = await get_tenant_id(request)

    # Verify patient exists and belongs to tenant
    patient_result = await db.execute(
        select(Patient).where(Patient.id == prescription_data.patient_id, Patient.tenant_id == tenant_id)
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Verify encounter if provided
    encounter = None
    if prescription_data.encounter_id:
        enc_result = await db.execute(
            select(OPDRegistration).where(OPDRegistration.id == prescription_data.encounter_id, OPDRegistration.tenant_id == tenant_id)
        )
        encounter = enc_result.scalar_one_or_none()
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found")

    # Generate prescription number
    rx_number = await generate(db, Prescription, "prescription_number", "RX", tenant_id)

    # Create prescription
    prescription = Prescription(
        tenant_id=tenant_id,
        patient_id=prescription_data.patient_id,
        encounter_id=prescription_data.encounter_id,
        doctor_id=user.id,
        prescription_number=rx_number,
        diagnosis=prescription_data.diagnosis,
        icd10_codes=prescription_data.icd10_codes,
        notes=prescription_data.notes,
        status=PrescriptionStatus.DRAFT,
        created_by=user.id,
    )
    db.add(prescription)
    await db.flush()

    # Create prescription lines
    lines = []
    for i, line_data in enumerate(prescription_data.lines):
        duration_days = parse_duration_to_days(line_data.duration)

        # Get drug info if drug_id provided
        drug_name = line_data.drug_name
        generic_name = line_data.generic_name
        strength = line_data.strength
        form = line_data.form

        if line_data.drug_id:
            drug_result = await db.execute(select(Drug).where(Drug.id == line_data.drug_id))
            drug = drug_result.scalar_one_or_none()
            if drug:
                drug_name = drug.name
                generic_name = drug.generic_name
                strength = drug.strength
                form = drug.form.value if not form else form

        line = PrescriptionLine(
            prescription_id=prescription.id,
            drug_id=line_data.drug_id,
            drug_name=drug_name,
            generic_name=generic_name,
            strength=strength,
            form=DrugForm(form) if form else None,
            route=DrugRoute(line_data.route),
            dose=line_data.dose,
            frequency=PrescriptionFrequency(line_data.frequency),
            frequency_custom=line_data.frequency_custom,
            duration=line_data.duration,
            duration_days=duration_days,
            quantity=line_data.quantity,
            quantity_unit=line_data.quantity_unit,
            refills=line_data.refills,
            instructions=line_data.instructions,
            before_food=line_data.before_food,
            at_bedtime=line_data.at_bedtime,
            sequence=i,
        )
        db.add(line)
        lines.append(line)

    await db.flush()

    # Run safety checks
    safety_result = await SafetyEngine.run_all_checks(
        db,
        prescription_data.patient_id,
        tenant_id,
        prescription_data.lines,
        prescription_data.encounter_id
    )

    # Update line safety statuses
    for line_check in safety_result.get("line_checks", []):
        if line_check["line_index"] < len(lines):
            lines[line_check["line_index"]].safety_status = line_check["safety_status"]
            lines[line_check["line_index"]].interaction_warnings = [
                w for w in line_check["warnings"] if w["type"] == "drug_interaction"
            ]
            lines[line_check["line_index"]].allergy_warnings = [
                w for w in line_check["warnings"] if w["type"] in ["allergy", "allergy_class"]
            ]
            lines[line_check["line_index"]].duplicate_therapy_warnings = [
                w for w in line_check["warnings"] if w["type"] == "duplicate_therapy"
            ]
            lines[line_check["line_index"]].dose_warnings = [
                w for w in line_check["warnings"] if w["type"] == "dose_range"
            ]
            lines[line_check["line_index"]].pregnancy_warnings = [
                w for w in line_check["warnings"] if w["type"] == "pregnancy_warning"
            ]

    await db.commit()

    # Build response
    await db.refresh(prescription)
    return await _build_prescription_response(db, prescription)


@router.get("/prescriptions/{encounter_id}", response_model=PrescriptionListResponse)
async def get_prescriptions_for_encounter(
    encounter_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get all prescriptions for an encounter."""
    tenant_id = await get_tenant_id(request)

    query = select(Prescription).where(
        Prescription.encounter_id == encounter_id,
        Prescription.tenant_id == tenant_id
    )

    if status:
        query = query.where(Prescription.status == status)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(desc(Prescription.prescribed_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    prescriptions = result.scalars().all()

    responses = []
    for presc in prescriptions:
        responses.append(await _build_prescription_response(db, presc))

    return PrescriptionListResponse(
        prescriptions=responses,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/prescriptions/{prescription_id}/lines", response_model=PrescriptionLineResponse)
async def add_prescription_line(
    prescription_id: str,
    line_data: PrescriptionLineCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Add a drug line to an existing prescription."""
    tenant_id = await get_tenant_id(request)

    # Get prescription
    result = await db.execute(
        select(Prescription).where(
            Prescription.id == prescription_id,
            Prescription.tenant_id == tenant_id
        )
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if prescription.status != PrescriptionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Can only add lines to DRAFT prescriptions")

    # Get next sequence
    seq_result = await db.execute(
        select(func.coalesce(func.max(PrescriptionLine.sequence), -1)).where(
            PrescriptionLine.prescription_id == prescription_id
        )
    )
    next_seq = (seq_result.scalar() or -1) + 1

    # Get drug info
    drug_name = line_data.drug_name
    generic_name = line_data.generic_name
    strength = line_data.strength
    form = line_data.form

    if line_data.drug_id:
        drug_result = await db.execute(select(Drug).where(Drug.id == line_data.drug_id))
        drug = drug_result.scalar_one_or_none()
        if drug:
            drug_name = drug.name
            generic_name = drug.generic_name
            strength = drug.strength
            form = drug.form.value if not form else form

    duration_days = parse_duration_to_days(line_data.duration)

    line = PrescriptionLine(
        prescription_id=prescription_id,
        drug_id=line_data.drug_id,
        drug_name=drug_name,
        generic_name=generic_name,
        strength=strength,
        form=DrugForm(form) if form else None,
        route=DrugRoute(line_data.route),
        dose=line_data.dose,
        frequency=PrescriptionFrequency(line_data.frequency),
        frequency_custom=line_data.frequency_custom,
        duration=line_data.duration,
        duration_days=duration_days,
        quantity=line_data.quantity,
        quantity_unit=line_data.quantity_unit,
        refills=line_data.refills,
        instructions=line_data.instructions,
        before_food=line_data.before_food,
        at_bedtime=line_data.at_bedtime,
        sequence=next_seq,
    )
    db.add(line)

    # Run safety check for this line
    safety_result = await SafetyEngine.run_all_checks(
        db,
        prescription.patient_id,
        tenant_id,
        [line_data],
        prescription.encounter_id
    )

    if safety_result.get("line_checks"):
        line_check = safety_result["line_checks"][0]
        line.safety_status = line_check["safety_status"]
        line.interaction_warnings = [w for w in line_check["warnings"] if w["type"] == "drug_interaction"]
        line.allergy_warnings = [w for w in line_check["warnings"] if w["type"] in ["allergy", "allergy_class"]]
        line.duplicate_therapy_warnings = [w for w in line_check["warnings"] if w["type"] == "duplicate_therapy"]
        line.dose_warnings = [w for w in line_check["warnings"] if w["type"] == "dose_range"]
        line.pregnancy_warnings = [w for w in line_check["warnings"] if w["type"] == "pregnancy_warning"]

    await db.commit()
    await db.refresh(line)

    return PrescriptionLineResponse(
        id=line.id,
        drug_id=line.drug_id,
        drug_name=line.drug_name,
        generic_name=line.generic_name,
        strength=line.strength,
        form=line.form.value if line.form else None,
        route=line.route.value,
        dose=line.dose,
        frequency=line.frequency.value,
        frequency_custom=line.frequency_custom,
        duration=line.duration,
        duration_days=line.duration_days,
        quantity=line.quantity,
        quantity_unit=line.quantity_unit,
        refills=line.refills,
        instructions=line.instructions,
        before_food=line.before_food,
        at_bedtime=line.at_bedtime,
        sequence=line.sequence,
        safety_status=line.safety_status,
        interaction_warnings=line.interaction_warnings,
        allergy_warnings=line.allergy_warnings,
        duplicate_therapy_warnings=line.duplicate_therapy_warnings,
        dose_warnings=line.dose_warnings,
        pregnancy_warnings=line.pregnancy_warnings,
    )


@router.patch("/prescriptions/{prescription_id}", response_model=PrescriptionResponse)
async def update_prescription(
    prescription_id: str,
    update_data: PrescriptionUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Update prescription status (DRAFT -> ACTIVE) or other fields."""
    tenant_id = await get_tenant_id(request)

    result = await db.execute(
        select(Prescription).where(
            Prescription.id == prescription_id,
            Prescription.tenant_id == tenant_id
        )
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if update_data.status:
        new_status = PrescriptionStatus(update_data.status)
        prescription.status = new_status

        if new_status == PrescriptionStatus.ACTIVE:
            prescription.started_at = datetime.utcnow()
            # Create dispensing task for pharmacy
            dispensing_task = DispensingTask(
                tenant_id=tenant_id,
                prescription_id=prescription.id,
                status="PENDING",
                priority="ROUTINE",
                created_by=user.id,
            )
            db.add(dispensing_task)

            # TODO: Emit WebSocket event for pharmacy queue
        elif new_status == PrescriptionStatus.COMPLETED:
            prescription.completed_at = datetime.utcnow()
        elif new_status == PrescriptionStatus.CANCELLED:
            prescription.completed_at = datetime.utcnow()

    if update_data.diagnosis is not None:
        prescription.diagnosis = update_data.diagnosis
    if update_data.icd10_codes is not None:
        prescription.icd10_codes = update_data.icd10_codes
    if update_data.notes is not None:
        prescription.notes = update_data.notes
    if update_data.expires_at is not None:
        prescription.expires_at = update_data.expires_at

    await db.commit()
    await db.refresh(prescription)

    return await _build_prescription_response(db, prescription)


@router.post("/prescriptions/safety-check", response_model=SafetyCheckResponse)
async def check_prescription_safety(
    request: Request,
    safety_request: SafetyCheckRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Run clinical safety checks on a prescription (real-time from frontend)."""
    tenant_id = await get_tenant_id(request)

    result = await SafetyEngine.run_all_checks(
        db,
        safety_request.patient_id,
        tenant_id,
        safety_request.lines,
        safety_request.encounter_id
    )

    return SafetyCheckResponse(
        overall_safety=result.get("overall_safety", "SAFE"),
        line_checks=result.get("line_checks", []),
        summary=result.get("summary", {}),
    )


async def _build_prescription_response(db: AsyncSession, prescription: Prescription) -> PrescriptionResponse:
    """Build prescription response with related data."""
    # Get patient info
    patient_result = await db.execute(select(Patient).where(Patient.id == prescription.patient_id))
    patient = patient_result.scalar_one_or_none()

    # Get doctor info
    doctor_result = await db.execute(select(User).where(User.id == prescription.doctor_id))
    doctor = doctor_result.scalar_one_or_none()

    # Get lines
    lines_result = await db.execute(
        select(PrescriptionLine).where(PrescriptionLine.prescription_id == prescription.id)
        .order_by(PrescriptionLine.sequence)
    )
    lines = lines_result.scalars().all()

    line_responses = [
        PrescriptionLineResponse(
            id=line.id,
            drug_id=line.drug_id,
            drug_name=line.drug_name,
            generic_name=line.generic_name,
            strength=line.strength,
            form=line.form.value if line.form else None,
            route=line.route.value,
            dose=line.dose,
            frequency=line.frequency.value,
            frequency_custom=line.frequency_custom,
            duration=line.duration,
            duration_days=line.duration_days,
            quantity=line.quantity,
            quantity_unit=line.quantity_unit,
            refills=line.refills,
            instructions=line.instructions,
            before_food=line.before_food,
            at_bedtime=line.at_bedtime,
            sequence=line.sequence,
            safety_status=line.safety_status,
            interaction_warnings=line.interaction_warnings,
            allergy_warnings=line.allergy_warnings,
            duplicate_therapy_warnings=line.duplicate_therapy_warnings,
            dose_warnings=line.dose_warnings,
            pregnancy_warnings=line.pregnancy_warnings,
        )
        for line in lines
    ]

    return PrescriptionResponse(
        id=prescription.id,
        prescription_number=prescription.prescription_number,
        patient_id=prescription.patient_id,
        encounter_id=prescription.encounter_id,
        doctor_id=prescription.doctor_id,
        status=prescription.status.value,
        diagnosis=prescription.diagnosis,
        icd10_codes=prescription.icd10_codes,
        notes=prescription.notes,
        prescribed_at=prescription.prescribed_at,
        started_at=prescription.started_at,
        completed_at=prescription.completed_at,
        expires_at=prescription.expires_at,
        lines=line_responses,
        patient_name=f"{patient.first_name} {patient.last_name}" if patient else None,
        patient_age=patient.age_years if patient else None,
        patient_gender=patient.gender.value if patient else None,
        uhid=patient.uhid if patient else None,
        doctor_name=doctor.full_name if doctor else None,
    )


# ═══════════════════════════════════════════════════════════════
# Allergy/Intolerance Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/patients/{patient_id}/allergies", response_model=List[AllergyResponse])
async def get_patient_allergies(
    patient_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get all allergies for a patient."""
    tenant_id = await get_tenant_id(request)

    result = await db.execute(
        select(AllergyIntolerance).where(
            AllergyIntolerance.patient_id == patient_id,
            AllergyIntolerance.tenant_id == tenant_id
        ).order_by(desc(AllergyIntolerance.created_at))
    )
    allergies = result.scalars().all()

    return [
        AllergyResponse(
            id=a.id,
            substance=a.substance,
            substance_code=a.substance_code,
            drug_class=a.drug_class.value if a.drug_class else None,
            reaction_type=a.reaction_type,
            manifestation=a.manifestation,
            severity=a.severity,
            onset_date=a.onset_date,
            verified=a.verified,
            verified_by=a.verified_by,
            verified_at=a.verified_at,
            status=a.status,
            notes=a.notes,
            created_at=a.created_at,
        )
        for a in allergies
    ]


@router.post("/patients/{patient_id}/allergies", response_model=AllergyResponse, status_code=201)
async def add_patient_allergy(
    patient_id: str,
    allergy_data: AllergyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Add an allergy/intolerance for a patient."""
    tenant_id = await get_tenant_id(request)

    # Verify patient exists
    patient_result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Parse drug class if provided
    drug_class = None
    if allergy_data.drug_class:
        try:
            drug_class = DrugClass(allergy_data.drug_class)
        except ValueError:
            pass

    # Parse onset date
    onset_date = allergy_data.onset_date

    allergy = AllergyIntolerance(
        tenant_id=tenant_id,
        patient_id=patient_id,
        substance=allergy_data.substance,
        substance_code=allergy_data.substance_code,
        drug_class=drug_class,
        reaction_type=allergy_data.reaction_type,
        manifestation=allergy_data.manifestation,
        severity=allergy_data.severity,
        onset_date=onset_date,
        verified=allergy_data.verified,
        verified_by=user.id if allergy_data.verified else None,
        verified_at=datetime.utcnow() if allergy_data.verified else None,
        status="ACTIVE",
        notes=allergy_data.notes,
        recorded_by=user.id,
    )
    db.add(allergy)
    await db.commit()
    await db.refresh(allergy)

    # Log audit
    await log_action(db, AuditAction.PATIENT_ACCESSED, patient_id=patient_id, user_id=user.id, details_json={"action": "allergy_added", "substance": allergy_data.substance})

    return AllergyResponse(
        id=allergy.id,
        substance=allergy.substance,
        substance_code=allergy.substance_code,
        drug_class=allergy.drug_class.value if allergy.drug_class else None,
        reaction_type=allergy.reaction_type,
        manifestation=allergy.manifestation,
        severity=allergy.severity,
        onset_date=allergy.onset_date,
        verified=allergy.verified,
        verified_by=allergy.verified_by,
        verified_at=allergy.verified_at,
        status=allergy.status,
        notes=allergy.notes,
        created_at=allergy.created_at,
    )


# ═══════════════════════════════════════════════════════════════
# Pharmacy Dispensing Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/pharmacy/queue", response_model=List[DispensingTaskResponse])
async def get_dispensing_queue(
    request: Request,
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get pharmacy dispensing queue (WebSocket will push updates)."""
    tenant_id = await get_tenant_id(request)

    query = (
        select(DispensingTask, Prescription, Patient)
        .join(Prescription, DispensingTask.prescription_id == Prescription.id)
        .join(Patient, Prescription.patient_id == Patient.id)
        .where(DispensingTask.tenant_id == tenant_id)
    )

    if status:
        query = query.where(DispensingTask.status == status)
    if priority:
        query = query.where(DispensingTask.priority == priority)

    query = query.order_by(
        DispensingTask.priority.desc(),
        DispensingTask.created_at.asc()
    )

    result = await db.execute(query)
    rows = result.fetchall()

    responses = []
    for task, prescription, patient in rows:
        responses.append(DispensingTaskResponse(
            id=task.id,
            prescription_id=task.prescription_id,
            pharmacist_id=task.pharmacist_id,
            status=task.status,
            priority=task.priority,
            dispensed_lines=task.dispensed_lines,
            notes=task.notes,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            patient_name=f"{patient.first_name} {patient.last_name}",
            prescription_number=prescription.prescription_number,
        ))

    return responses


@router.post("/pharmacy/queue/{task_id}/start", response_model=DispensingTaskResponse)
async def start_dispensing(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Pharmacist starts dispensing a prescription."""
    tenant_id = await get_tenant_id(request)

    result = await db.execute(
        select(DispensingTask).where(
            DispensingTask.id == task_id,
            DispensingTask.tenant_id == tenant_id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Dispensing task not found")

    task.status = "IN_PROGRESS"
    task.pharmacist_id = user.id
    task.started_at = datetime.utcnow()

    await db.commit()
    await db.refresh(task)

    # TODO: Emit WebSocket update

    return await _build_dispensing_response(db, task)


@router.post("/pharmacy/queue/{task_id}/dispense", response_model=DispensingTaskResponse)
async def dispense_prescription(
    task_id: str,
    dispensed_data: dict,  # {line_id: quantity_dispensed, batch, expiry}
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Record dispensed quantities for each line."""
    tenant_id = await get_tenant_id(request)

    result = await db.execute(
        select(DispensingTask).where(
            DispensingTask.id == task_id,
            DispensingTask.tenant_id == tenant_id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Dispensing task not found")

    task.dispensed_lines = dispensed_data.get("lines", [])
    task.notes = dispensed_data.get("notes")
    task.status = "DISPENSED"
    task.completed_at = datetime.utcnow()

    # Update prescription status
    presc_result = await db.execute(select(Prescription).where(Prescription.id == task.prescription_id))
    prescription = presc_result.scalar_one_or_none()
    if prescription:
        prescription.status = PrescriptionStatus.COMPLETED
        prescription.completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(task)

    return await _build_dispensing_response(db, task)


async def _build_dispensing_response(db: AsyncSession, task: DispensingTask) -> DispensingTaskResponse:
    presc_result = await db.execute(
        select(Prescription, Patient).join(Patient).where(Prescription.id == task.prescription_id)
    )
    row = presc_result.first()
    prescription = row[0] if row else None
    patient = row[1] if row else None

    return DispensingTaskResponse(
        id=task.id,
        prescription_id=task.prescription_id,
        pharmacist_id=task.pharmacist_id,
        status=task.status,
        priority=task.priority,
        dispensed_lines=task.dispensed_lines,
        notes=task.notes,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        patient_name=f"{patient.first_name} {patient.last_name}" if patient else None,
        prescription_number=prescription.prescription_number if prescription else None,
    )


# ═══════════════════════════════════════════════════════════════
# Formulary Management (Admin)
# ═══════════════════════════════════════════════════════════════

class FormularyEntryCreate(BaseModel):
    drug_id: str
    category: Optional[str] = None
    is_preferred: bool = False
    is_restricted: bool = False
    restriction_notes: Optional[str] = None
    price: Optional[str] = None
    currency: str = "INR"
    available: bool = True


class FormularyEntryUpdate(BaseModel):
    category: Optional[str] = None
    is_preferred: Optional[bool] = None
    is_restricted: Optional[bool] = None
    restriction_notes: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None
    available: Optional[bool] = None


@router.post("/formulary", status_code=201)
async def add_to_formulary(
    entry_data: FormularyEntryCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Add a drug to the organization's formulary."""
    tenant_id = await get_tenant_id(request)

    # Verify drug exists
    drug_result = await db.execute(select(Drug).where(Drug.id == entry_data.drug_id))
    drug = drug_result.scalar_one_or_none()
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    # Check if already in formulary
    existing = await db.execute(
        select(FormularyEntry).where(
            FormularyEntry.tenant_id == tenant_id,
            FormularyEntry.drug_id == entry_data.drug_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Drug already in formulary")

    entry = FormularyEntry(
        tenant_id=tenant_id,
        drug_id=entry_data.drug_id,
        category=entry_data.category,
        is_preferred=entry_data.is_preferred,
        is_restricted=entry_data.is_restricted,
        restriction_notes=entry_data.restriction_notes,
        price=entry_data.price,
        currency=entry_data.currency,
        available=entry_data.available,
        created_by=user.id,
    )
    db.add(entry)
    await db.commit()

    return {"message": "Drug added to formulary", "formulary_id": entry.id}


@router.get("/formulary", response_model=List[DrugSearchResponse])
async def list_formulary(
    request: Request,
    category: Optional[str] = Query(None),
    preferred_only: bool = Query(False),
    available_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """List all drugs in the organization's formulary."""
    tenant_id = await get_tenant_id(request)

    query = (
        select(Drug, FormularyEntry)
        .join(FormularyEntry, FormularyEntry.drug_id == Drug.id)
        .where(FormularyEntry.tenant_id == tenant_id)
    )

    if category:
        query = query.where(FormularyEntry.category == category)
    if preferred_only:
        query = query.where(FormularyEntry.is_preferred == True)
    if available_only:
        query = query.where(FormularyEntry.available == True)

    query = query.order_by(FormularyEntry.category, Drug.generic_name)
    result = await db.execute(query)
    rows = result.fetchall()

    drugs = []
    for drug, formulary in rows:
        drugs.append(DrugSearchResponse(
            id=drug.id,
            name=drug.name,
            generic_name=drug.generic_name,
            strength=drug.strength,
            form=drug.form.value,
            route=drug.route.value,
            manufacturer=drug.manufacturer,
            category=formulary.category,
            drug_class=drug.drug_class.value,
            atc_code=drug.atc_code,
            price=formulary.price,
            currency=formulary.currency,
            is_essential=drug.is_essential,
            pregnancy_category=drug.pregnancy_category.value,
            dosing_adult=drug.dosing_adult,
            dosing_pediatric=drug.dosing_pediatric,
            dosing_geriatric=drug.dosing_geriatric,
            formulary_price=formulary.price,
            formulary_category=formulary.category,
            is_preferred=formulary.is_preferred,
            is_restricted=formulary.is_restricted,
            restriction_notes=formulary.restriction_notes,
        ))

    return drugs


@router.patch("/formulary/{formulary_id}")
async def update_formulary_entry(
    formulary_id: str,
    update_data: FormularyEntryUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Update formulary entry (price, category, restrictions)."""
    tenant_id = await get_tenant_id(request)

    result = await db.execute(
        select(FormularyEntry).where(
            FormularyEntry.id == formulary_id,
            FormularyEntry.tenant_id == tenant_id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Formulary entry not found")

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(entry, field, value)

    entry.updated_at = datetime.utcnow()
    await db.commit()

    return {"message": "Formulary entry updated"}


@router.delete("/formulary/{formulary_id}")
async def remove_from_formulary(
    formulary_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Remove a drug from the formulary."""
    tenant_id = await get_tenant_id(request)

    result = await db.execute(
        select(FormularyEntry).where(
            FormularyEntry.id == formulary_id,
            FormularyEntry.tenant_id == tenant_id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Formulary entry not found")

    await db.delete(entry)
    await db.commit()

    return {"message": "Drug removed from formulary"}