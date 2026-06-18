"""HealthBridge Platform — FHIR R4 API Routes"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional

from app.database import get_db, AsyncSession
from app.models import Patient, PatientRecord, RecordType
from app.services.fhir_conversion import FhirConversionService
from app.security.rbac import require_permission
from sqlalchemy import select
import json

router = APIRouter(prefix="/fhir", tags=["FHIR R4"])

conversion_service = FhirConversionService()


# ── Standard FHIR R4 Endpoints ──

@router.get("/{resource_type}/{resource_id}")
async def read_resource(
    resource_type: str,
    resource_id: str,
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Read a FHIR resource by ID."""
    result = await db.execute(
        select(PatientRecord).where(
            PatientRecord.fhir_resource_type == resource_type,
            PatientRecord.id == resource_id,
            PatientRecord.is_active
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail=f"{resource_type}/{resource_id} not found")

    if record.fhir_resource_json:
        return json.loads(record.fhir_resource_json)

    # Build FHIR resource on the fly
    bundle_str = conversion_service.build_fhir_bundle_from_record(record)
    if bundle_str:
        bundle = json.loads(bundle_str)
        if bundle.get("entry"):
            for entry in bundle["entry"]:
                res = entry.get("resource", {})
                if res.get("id") == resource_id:
                    return res

    raise HTTPException(status_code=404, detail="FHIR resource not available")


@router.get("/{resource_type}")
async def search_resource(
    resource_type: str,
    patient: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Search FHIR resources."""
    from sqlalchemy import select, or_

    query = select(PatientRecord).where(
        PatientRecord.fhir_resource_type == resource_type,
        PatientRecord.is_active
    )

    if patient:
        query = query.where(PatientRecord.patient_id == patient)
    if code:
        query = query.where(PatientRecord.code == code)
    if name:
        # Search by display name or clinical summary
        query = query.where(
            or_(
                PatientRecord.display_name.ilike(f"%{name}%"),
                PatientRecord.clinical_summary.ilike(f"%{name}%"),
            )
        )

    query = query.limit(limit).order_by(PatientRecord.recorded_date.desc().nullslast())
    result = await db.execute(query)
    records = result.scalars().all()

    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(records),
        "entry": []
    }

    for record in records:
        if record.fhir_resource_json:
            resource = json.loads(record.fhir_resource_json)
        else:
            # Minimal FHIR resource
            resource = {
                "resourceType": resource_type,
                "id": record.id,
                "code": {
                "coding": [{
                        "system": record.code_system,
                        "code": record.code,
                        "display": record.display_name,
                    }] if record.code else []
                } if record_type_needs_code(resource_type) else {},
                "subject": {"reference": f"Patient/{record.patient_id}"},
                "recordedDate": record.recorded_date.isoformat() if record.recorded_date else None,
            }
            if record.clinical_summary and resource_type == "Condition":
                resource["clinicalStatus"] = {"coding": [{"code": "active", "display": record.clinical_summary}]}

        bundle["entry"].append({
            "fullUrl": f"urn:uuid:{record.id}",
            "resource": resource,
        })

    return bundle


@router.post("/{resource_type}")
async def create_resource(
    resource_type: str,
    request: Request,
    current_user = Depends(require_permission("patient.write")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new FHIR resource."""
    body = await request.json()

    # Determine patient from resource
    patient_ref = None
    if "subject" in body and body["subject"].get("reference", "").startswith("Patient/"):
        patient_ref = body["subject"]["reference"].split("/")[1]
    elif "patient" in body and body["patient"].get("reference", "").startswith("Patient/"):
        patient_ref = body["patient"]["reference"].split("/")[1]

    if not patient_ref:
        raise HTTPException(status_code=400, detail="Resource must reference a Patient")

    import uuid
    record_id = str(uuid.uuid4())
    record = PatientRecord(
        id=record_id,
        patient_id=patient_ref,
        record_type=map_fhir_to_record_type(resource_type),
        fhir_resource_type=resource_type,
        fhir_resource_json=json.dumps(body),
        source_system="HEALTHBRIDGE_API",
        source_type="EHR",
        clinical_summary=body.get("code", {}).get("text") or body.get("clinicalStatus", {}).get("coding", [{}])[0].get("display"),
        code=body.get("code", {}).get("coding", [{}])[0].get("code") if "code" in body else None,
        code_system=body.get("code", {}).get("coding", [{}])[0].get("system") if "code" in body else None,
        display_name=body.get("code", {}).get("coding", [{}])[0].get("display") if "code" in body else None,
        ingested_by=current_user.id,
    )
    db.add(record)
    await db.flush()

    return {"resourceType": resource_type, "id": record_id, "created": True}


def map_fhir_to_record_type(fhir_type: str) -> RecordType:
    mapping = {
        "Condition": RecordType.CONDITION,
        "MedicationRequest": RecordType.MEDICATION_REQUEST,
        "MedicationStatement": RecordType.MEDICATION_STATEMENT,
        "Observation": RecordType.OBSERVATION,
        "DiagnosticReport": RecordType.DIAGNOSTIC_REPORT,
        "Procedure": RecordType.PROCEDURE,
        "Encounter": RecordType.ENCOUNTER,
        "AllergyIntolerance": RecordType.ALLERGY_INTOLERANCE,
        "Immunization": RecordType.IMMUNIZATION,
        "DocumentReference": RecordType.DOCUMENT_REFERENCE,
    }
    return mapping.get(fhir_type, RecordType.OBSERVATION)


def record_type_needs_code(rt: str) -> bool:
    return rt in ("Condition", "Observation", "MedicationRequest", "Procedure",
                  "AllergyIntolerance", "Immunization", "DiagnosticReport")


# ── Patient-level FHIR Bundle ──

@router.get("/Patient/{patient_id}/$everything")
async def get_patient_everything(
    patient_id: str,
    current_user = Depends(require_permission("patient.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get all FHIR resources for a patient (similar to FHIR $everything operation)."""
    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get all records
    records_result = await db.execute(
        select(PatientRecord).where(
            PatientRecord.patient_id == patient_id,
            PatientRecord.is_active
        ).order_by(PatientRecord.recorded_date.desc().nullslast())
    )
    records = records_result.scalars().all()

    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "id": f"urn:uuid:{patient_id}",
        "total": len(records) + 1,
        "entry": [
            {
                "fullUrl": f"urn:uuid:{patient_id}",
                "resource": {
                    "resourceType": "Patient",
                    "id": patient_id,
                    "identifier": [
                        {"system": "urn:healthbridge:mrn", "value": patient.mrn},
                    ],
                    "name": [{"family": patient.last_name, "given": [patient.first_name]}],
                    "gender": patient.gender.value.lower() if patient.gender else "unknown",
                    "birthDate": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                }
            }
        ]
    }

    for record in records:
        if record.fhir_resource_json:
            try:
                resource = json.loads(record.fhir_resource_json)
            except json.JSONDecodeError:
                continue
        else:
            resource = {
                "resourceType": record.fhir_resource_type or "Observation",
                "id": record.id,
                "subject": {"reference": f"Patient/{patient_id}"},
                "code": {
                    "coding": [{
                        "system": record.code_system,
                        "code": record.code,
                        "display": record.display_name,
                    }] if record.code else []
                } if record.code else {"text": record.clinical_summary},
                "recordedDate": record.recorded_date.isoformat() if record.recorded_date else None,
                "encounter": {"reference": f"Encounter/{record.id}"} if record.encounter_date else None,
            }

        bundle["entry"].append({
            "fullUrl": f"urn:uuid:{record.id}",
            "resource": resource,
        })

    return bundle
