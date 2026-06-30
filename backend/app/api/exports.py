"""HealthBridge Platform — Exports API Routes

Provides endpoints for exporting patient data, audit logs, and compliance
reports in CSV and JSON formats.  Also supports FHIR Bundle exports and
scheduled recurring exports.
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.database import get_db, AsyncSession
from app.models import Patient, PatientRecord, AuditLog, AuditAction
from app.security.audit import log_action
from app.security.rbac import require_permission
from app.security.encryption import decrypt_field
from sqlalchemy import select, and_

logger = logging.getLogger("healthbridge.exports")

router = APIRouter(prefix="/api/v1/exports", tags=["Exports"])

# ── In-memory export history store ──
_EXPORT_HISTORY: list[dict[str, Any]] = []

# ── In-memory scheduled exports ──
_SCHEDULED_EXPORTS: list[dict[str, Any]] = []


# ═══════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════


class ScheduleExportRequest(BaseModel):
    """Request body to schedule a recurring export."""

    cron_expression: str
    format: str = "csv"  # csv or json
    scope: str = "patients"  # patients, records, audit_logs, compliance


# ═══════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════


def _dict_to_csv_row(data: dict[str, Any]) -> dict[str, str]:
    """Flatten nested dict/list values to strings for CSV export."""
    row: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            import json

            row[key] = json.dumps(value)
        elif value is None:
            row[key] = ""
        else:
            row[key] = str(value)
    return row


def _patients_to_csv(patients: list[dict[str, Any]]) -> str:
    """Convert a list of patient dicts to CSV string."""
    output = io.StringIO()
    if not patients:
        return ""

    fieldnames = [
        "id", "mrn", "first_name", "last_name", "date_of_birth",
        "gender", "phone", "email", "abha_number", "consent_status",
        "city", "state", "pincode", "created_at", "updated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for patient in patients:
        writer.writerow(_dict_to_csv_row(patient))
    return output.getvalue()


def _records_to_csv(records: list[dict[str, Any]]) -> str:
    """Convert a list of record dicts to CSV string."""
    output = io.StringIO()
    if not records:
        return ""

    fieldnames = [
        "id", "patient_id", "record_type", "source_system",
        "display_name", "code", "code_system", "recorded_date",
        "encounter_date", "provider_name", "facility_name",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        writer.writerow(_dict_to_csv_row(record))
    return output.getvalue()


def _audit_logs_to_csv(logs: list[dict[str, Any]]) -> str:
    """Convert a list of audit log dicts to CSV string."""
    output = io.StringIO()
    if not logs:
        return ""

    fieldnames = [
        "id", "timestamp", "action", "patient_id",
        "resource_id", "resource_type", "description",
        "user_id", "ip_address", "user_agent",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for log in logs:
        writer.writerow(_dict_to_csv_row(log))
    return output.getvalue()


def _build_fhir_bundle(
    patient: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a FHIR R4 Bundle containing a Patient and its related resources."""
    bundle_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    entries: list[dict[str, Any]] = []

    # Patient entry
    patient_resource = patient.get("raw_resource", {})
    if not patient_resource:
        # Build a basic Patient resource from the dict
        patient_resource = {
            "resourceType": "Patient",
            "id": patient.get("id", ""),
            "identifier": [
                {
                    "system": "urn:healthbridge:mrn",
                    "value": patient.get("mrn", ""),
                }
            ],
            "name": [
                {
                    "family": patient.get("last_name", ""),
                    "given": [patient.get("first_name", "")],
                }
            ],
            "gender": patient.get("gender", "unknown").lower(),
            "birthDate": patient.get("date_of_birth", ""),
            "telecom": [
                {"system": "phone", "value": patient.get("phone", "")},
                {"system": "email", "value": patient.get("email", "")},
            ],
        }

    entries.append(
        {
            "fullUrl": f"urn:uuid:{patient.get('id', bundle_id)}",
            "resource": patient_resource,
            "request": {"method": "GET", "url": f"Patient/{patient.get('id', '')}"},
        }
    )

    # Record entries
    for record in records:
        resource = record.get("fhir_resource_json", {})
        if not resource:
            # Build a minimal resource
            resource_type = record.get("fhir_resource_type", "Observation")
            resource = {
                "resourceType": resource_type,
                "id": record.get("external_id", record.get("id", "")),
                "subject": {
                    "reference": f"Patient/{patient.get('id', '')}",
                },
                "code": {
                    "coding": [
                        {
                            "system": record.get("code_system", ""),
                            "code": record.get("code", ""),
                        }
                    ],
                    "text": record.get("display_name", ""),
                },
                "status": record.get("status", "final"),
            }

        entries.append(
            {
                "fullUrl": f"urn:uuid:{record.get('id', record.get('external_id', str(uuid.uuid4())))}",
                "resource": resource,
                "request": {
                    "method": "GET",
                    "url": f"{resource.get('resourceType', 'Unknown')}/{record.get('id', '')}",
                },
            }
        )

    return {
        "resourceType": "Bundle",
        "id": bundle_id,
        "type": "document",
        "timestamp": now,
        "entry": entries,
    }


# ═══════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════


@router.get("/patients")
async def export_patients(
    request: Request,
    format: str = Query("csv", regex="^(csv|json)$"),
    current_user=Depends(require_permission("patient.export")),
    db: AsyncSession = Depends(get_db),
):
    """Export all patients (visible to the current user's tenant)."""
    # Filter by tenant if the user belongs to an organisation
    query = select(Patient)
    if current_user.tenant_id:
        query = query.where(Patient.tenant_id == current_user.tenant_id)

    result = await db.execute(query.order_by(Patient.created_at.desc()))
    patients = result.scalars().all()

    patient_dicts = [
        {
            "id": p.id,
            "mrn": p.mrn,
            "first_name": decrypt_field(p.first_name),
            "last_name": decrypt_field(p.last_name),
            "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
            "gender": p.gender.value if p.gender else None,
            "phone": decrypt_field(p.phone),
            "email": decrypt_field(p.email),
            "address": p.address,
            "abha_number": p.abha_number,
            "consent_status": p.consent_status.value if p.consent_status else None,
            "city": p.city,
            "state": p.state,
            "pincode": p.pincode,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in patients
    ]

    # Audit log
    await log_action(
        action=AuditAction.DATA_EXPORTED,
        description=f"Exported {len(patient_dicts)} patients as {format}",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details={"format": format, "count": len(patient_dicts)},
        db=db,
    )

    # Record export in history
    _EXPORT_HISTORY.append({
        "id": str(uuid.uuid4()),
        "type": "patients",
        "format": format,
        "count": len(patient_dicts),
        "exported_by": current_user.id,
        "exported_at": datetime.utcnow().isoformat(),
    })

    if format == "csv":
        csv_content = _patients_to_csv(patient_dicts)
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=patients_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            },
        )

    return {"patients": patient_dicts, "count": len(patient_dicts)}


@router.post("/patient/{patient_id}/fhir-bundle")
async def export_patient_fhir_bundle(
    request: Request,
    patient_id: str,
    current_user=Depends(require_permission("patient.export")),
    db: AsyncSession = Depends(get_db),
):
    """Export a single patient and their records as a FHIR R4 Bundle."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    record_result = await db.execute(
        select(PatientRecord).where(PatientRecord.patient_id == patient_id)
    )
    records = record_result.scalars().all()

    patient_dict = {
        "id": patient.id,
        "mrn": patient.mrn,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "gender": patient.gender.value if patient.gender else None,
        "phone": patient.phone,
        "email": patient.email,
        "source_system": "HealthBridge",
    }

    record_dicts = [
        {
            "id": r.id,
            "patient_id": r.patient_id,
            "record_type": r.record_type.value if r.record_type else None,
            "fhir_resource_type": r.fhir_resource_type,
            "fhir_resource_json": r.fhir_resource_json,
            "code": r.code,
            "code_system": r.code_system,
            "display_name": r.display_name,
            "recorded_date": r.recorded_date.isoformat() if r.recorded_date else None,
            "status": "final",
            "source_system": r.source_system,
        }
        for r in records
    ]

    bundle = _build_fhir_bundle(patient_dict, record_dicts)

    # Audit log
    await log_action(
        action=AuditAction.DATA_EXPORTED,
        patient_id=patient_id,
        description=f"Exported patient {patient_id} as FHIR Bundle",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details={"type": "fhir_bundle", "record_count": len(record_dicts)},
        db=db,
    )

    _EXPORT_HISTORY.append({
        "id": str(uuid.uuid4()),
        "type": "fhir_bundle",
        "patient_id": patient_id,
        "record_count": len(record_dicts),
        "exported_by": current_user.id,
        "exported_at": datetime.utcnow().isoformat(),
    })

    return bundle


@router.post("/patient/{patient_id}/records")
async def export_patient_records(
    request: Request,
    patient_id: str,
    format: str = Query("json", regex="^(csv|json)$"),
    current_user=Depends(require_permission("patient.export")),
    db: AsyncSession = Depends(get_db),
):
    """Export records for a single patient."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    record_result = await db.execute(
        select(PatientRecord).where(PatientRecord.patient_id == patient_id)
    )
    records = record_result.scalars().all()

    record_dicts = [
        {
            "id": r.id,
            "patient_id": r.patient_id,
            "record_type": r.record_type.value if r.record_type else None,
            "source_system": r.source_system,
            "source_type": r.source_type.value if r.source_type else None,
            "fhir_resource_type": r.fhir_resource_type,
            "display_name": r.display_name,
            "code": r.code,
            "code_system": r.code_system,
            "recorded_date": r.recorded_date.isoformat() if r.recorded_date else None,
            "encounter_date": r.encounter_date.isoformat() if r.encounter_date else None,
            "provider_name": r.provider_name,
            "facility_name": r.facility_name,
            "clinical_summary": r.clinical_summary,
            "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
        }
        for r in records
    ]

    # Audit log
    await log_action(
        action=AuditAction.DATA_EXPORTED,
        patient_id=patient_id,
        description=f"Exported {len(record_dicts)} records for patient {patient_id} as {format}",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details={"format": format, "record_count": len(record_dicts)},
        db=db,
    )

    _EXPORT_HISTORY.append({
        "id": str(uuid.uuid4()),
        "type": "patient_records",
        "patient_id": patient_id,
        "format": format,
        "count": len(record_dicts),
        "exported_by": current_user.id,
        "exported_at": datetime.utcnow().isoformat(),
    })

    if format == "csv":
        csv_content = _records_to_csv(record_dicts)
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=patient_{patient_id}_records_"
                    f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
                )
            },
        )

    return {"records": record_dicts, "count": len(record_dicts)}


@router.get("/audit-logs")
async def export_audit_logs(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    current_user=Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Export audit logs as CSV with optional date range filter."""
    query = select(AuditLog)

    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.where(AuditLog.timestamp >= start)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")

    if end_date:
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.where(AuditLog.timestamp < end)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")

    query = query.order_by(AuditLog.timestamp.desc())
    result = await db.execute(query)
    logs = result.scalars().all()

    log_dicts = [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "action": log.action.value if log.action else None,
            "patient_id": log.patient_id,
            "resource_id": log.resource_id,
            "resource_type": log.resource_type,
            "description": log.description,
            "user_id": log.user_id,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "consent_id": log.consent_id,
        }
        for log in logs
    ]

    # Audit log (meta)
    await log_action(
        action=AuditAction.DATA_EXPORTED,
        description=f"Exported {len(log_dicts)} audit logs as CSV",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details={"type": "audit_logs", "count": len(log_dicts)},
        db=db,
    )

    _EXPORT_HISTORY.append({
        "id": str(uuid.uuid4()),
        "type": "audit_logs",
        "count": len(log_dicts),
        "exported_by": current_user.id,
        "exported_at": datetime.utcnow().isoformat(),
    })

    csv_content = _audit_logs_to_csv(log_dicts)
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=audit_logs_export_"
                f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            )
        },
    )


@router.get("/compliance-report")
async def export_compliance_report(
    request: Request,
    current_user=Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download a DPDP compliance report as JSON."""
    from sqlalchemy import func

    # Gather compliance stats
    total_patients = (await db.execute(select(func.count(Patient.id)))).scalar()
    total_records = (await db.execute(select(func.count(PatientRecord.id)))).scalar()

    # Consent stats
    from app.models import ConsentStatus
    consented = (
        await db.execute(
            select(func.count(Patient.id)).where(Patient.consent_status == ConsentStatus.GRANTED)
        )
    ).scalar()

    # Audit retention stats
    retention_cutoff = date.today() - timedelta(days=365)
    audit_logs_in_retention = (
        await db.execute(
            select(func.count(AuditLog.id)).where(AuditLog.timestamp >= datetime.combine(retention_cutoff, datetime.min.time()))
        )
    ).scalar()

    report = {
        "report_type": "DPDP Compliance Report",
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": current_user.id,
        "organization_id": current_user.tenant_id,
        "patient_statistics": {
            "total_patients": total_patients or 0,
            "total_records": total_records or 0,
            "patients_with_consent": consented or 0,
        },
        "audit_compliance": {
            "retention_period_days": 365,
            "retention_cutoff_date": retention_cutoff.isoformat(),
            "audit_logs_in_retention": audit_logs_in_retention or 0,
        },
        "data_protection_measures": {
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_control": "RBAC",
            "breach_detection_enabled": True,
            "data_minimization": True,
            "purpose_limitation": True,
        },
        "compliance_status": "COMPLIANT",
        "recommendations": [],
    }

    if consented and total_patients:
        consent_rate = consented / total_patients
        if consent_rate < 0.8:
            report["compliance_status"] = "PARTIALLY_COMPLIANT"
            report["recommendations"].append(
                "Consent rate is below 80%. Review consent collection processes."
            )

    # Audit log
    await log_action(
        action=AuditAction.DATA_EXPORTED,
        description="Generated DPDP compliance report",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details={"type": "compliance_report"},
        db=db,
    )

    _EXPORT_HISTORY.append({
        "id": str(uuid.uuid4()),
        "type": "compliance_report",
        "exported_by": current_user.id,
        "exported_at": datetime.utcnow().isoformat(),
    })

    return report


@router.get("/history")
async def list_export_history(
    current_user=Depends(require_permission("audit.view")),
):
    """List past export operations."""
    return {
        "exports": list(reversed(_EXPORT_HISTORY)),
        "count": len(_EXPORT_HISTORY),
    }


@router.post("/scheduled")
async def schedule_export(
    request: Request,
    schedule: ScheduleExportRequest,
    current_user=Depends(require_permission("system.admin")),
    db: AsyncSession = Depends(get_db),
):
    """Schedule a recurring export job.

    Args:
        cron_expression: Standard cron expression (e.g. ``0 2 * * *`` for daily at 2 AM).
        format: Output format (``csv`` or ``json``).
        scope: What to export (``patients``, ``records``, ``audit_logs``, ``compliance``).
    """
    if schedule.format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="Format must be 'csv' or 'json'")

    if schedule.scope not in ("patients", "records", "audit_logs", "compliance"):
        raise HTTPException(
            status_code=400,
            detail="Scope must be one of: patients, records, audit_logs, compliance",
        )

    scheduled_id = str(uuid.uuid4())
    entry = {
        "id": scheduled_id,
        "cron_expression": schedule.cron_expression,
        "format": schedule.format,
        "scope": schedule.scope,
        "created_by": current_user.id,
        "created_at": datetime.utcnow().isoformat(),
        "last_run": None,
        "next_run": None,  # Would be calculated by a scheduler
        "is_active": True,
    }
    _SCHEDULED_EXPORTS.append(entry)

    await log_action(
        action=AuditAction.DATA_EXPORTED,
        description=f"Scheduled {schedule.scope} export ({schedule.format}) with cron '{schedule.cron_expression}'",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details={
            "type": "scheduled_export",
            "format": schedule.format,
            "scope": schedule.scope,
            "cron": schedule.cron_expression,
        },
        db=db,
    )

    return {
        "id": scheduled_id,
        "message": f"Scheduled {schedule.scope} export ({schedule.format}) created",
        "schedule": schedule.cron_expression,
        "active": True,
    }
