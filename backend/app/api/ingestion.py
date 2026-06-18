"""HealthBridge Platform — Document Ingestion API Routes

Upload a photo/scan of a hospital document (prescription, lab report,
pharmacy bill, discharge summary) and get back a structured FHIR R4 Bundle.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import IngestionLog, Patient
from app.security.rbac import require_permission
from app.services.document_ingestion import (
    DOCUMENT_TYPES,
    process_document,
)

logger = logging.getLogger("healthbridge.api.ingestion")

router = APIRouter(prefix="/api/v1/ingest", tags=["Document Ingestion"])


@router.get("/types")
async def list_document_types():
    """List supported document types for ingestion."""
    return {
        "types": [{"id": k, "description": v} for k, v in DOCUMENT_TYPES.items()]
    }


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("general"),
    patient_id: Optional[str] = Form(None),
    current_user=Depends(require_permission("patient.write")),
    db: AsyncSession = Depends(get_db),
):
    """Upload a hospital document photo/scan and process it.

    The document goes through:
      1. OCR (Tesseract) → raw text
      2. AI extraction (LLM) → structured JSON
      3. FHIR conversion → R4 Bundle

    Returns the FHIR Bundle which can be stored as patient records.
    """
    # Validate document type
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported document type '{document_type}'. "
                   f"Supported: {', '.join(DOCUMENT_TYPES.keys())}",
        )

    # Validate file type
    allowed_types = {
        "image/jpeg", "image/png", "image/webp",
        "application/pdf", "image/tiff",
    }
    # Allow if content_type is missing (some clients don't send it)
    if file.content_type and file.content_type not in allowed_types:
        # Check filename extension as fallback
        ext = (file.filename or "").lower()
        if not any(ext.endswith(e) for e in [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".pdf"]):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{file.content_type}'. "
                       f"Supported: JPEG, PNG, WebP, TIFF, PDF",
            )

    # Validate patient exists if specified
    if patient_id:
        result = await db.execute(select(Patient).where(Patient.id == patient_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Patient not found")

    # Read file
    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Process document
    try:
        pipe_result = await process_document(
            image_bytes=image_bytes,
            filename=file.filename or "upload",
            document_type=document_type,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.exception("Document processing failed")
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    # Log to ingestion_logs table
    log_entry = IngestionLog(
        document_type=document_type,
        source_format="photo",
        original_filename=file.filename or "unknown",
        file_path=pipe_result.get("file_path"),
        file_size_bytes=pipe_result.get("file_size_bytes"),
        ocr_text=pipe_result.get("ocr_text"),
        extracted_json=pipe_result.get("extracted"),
        confidence_score=pipe_result.get("confidence_score"),
        status=pipe_result.get("status", "FAILED"),
        error_message=pipe_result.get("error_message"),
        processing_time_ms=pipe_result.get("processing_time_ms"),
        created_by=current_user.id if current_user else None,
    )

    # If processing succeeded and patient_id was given, link the log
    if pipe_result.get("status") == "PROCESSED" and patient_id:
        log_entry.patient_id = patient_id

    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

    return {
        "ingestion_id": log_entry.id,
        "status": pipe_result.get("status"),
        "document_type": document_type,
        "ocr_text_length": len(pipe_result.get("ocr_text", "") or ""),
        "confidence_score": pipe_result.get("confidence_score"),
        "processing_time_ms": pipe_result.get("processing_time_ms"),
        "extracted_data": pipe_result.get("extracted"),
        "fhir_bundle": pipe_result.get("fhir_bundle"),
        "patient_id": patient_id,
        "error": pipe_result.get("error_message"),
    }


@router.get("/logs")
async def list_ingestion_logs(
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[str] = None,
    current_user=Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """List document ingestion history."""
    query = select(IngestionLog).order_by(IngestionLog.created_at.desc())

    if status_filter:
        query = query.where(IngestionLog.status == status_filter)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "document_type": log.document_type,
            "original_filename": log.original_filename,
            "status": log.status,
            "confidence_score": log.confidence_score,
            "processing_time_ms": log.processing_time_ms,
            "patient_id": log.patient_id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "error_message": log.error_message,
        }
        for log in logs
    ]


@router.get("/logs/{log_id}")
async def get_ingestion_log(
    log_id: str,
    current_user=Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed ingestion log with extracted data."""
    result = await db.execute(select(IngestionLog).where(IngestionLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Ingestion log not found")

    return {
        "id": log.id,
        "patient_id": log.patient_id,
        "document_type": log.document_type,
        "source_format": log.source_format,
        "original_filename": log.original_filename,
        "file_path": log.file_path,
        "file_size_bytes": log.file_size_bytes,
        "ocr_text": log.ocr_text,
        "extracted_data": log.extracted_json,
        "confidence_score": log.confidence_score,
        "fhir_resource_type": log.fhir_resource_type,
        "fhir_resource_id": log.fhir_resource_id,
        "status": log.status,
        "error_message": log.error_message,
        "processing_time_ms": log.processing_time_ms,
        "created_by": log.created_by,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
