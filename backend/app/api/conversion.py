"""HealthBridge Platform — Document Conversion API Routes"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app.services.fhir_conversion import FhirConversionService
from app.security.auth import get_current_active_user

router = APIRouter(prefix="/api/v1/convert", tags=["Document Conversion"])

conversion_service = FhirConversionService()


# ── Schemas ──

class FhirToCcdaRequest(BaseModel):
    fhirBundleJson: str

class FhirToPdfRequest(BaseModel):
    fhirJson: str
    includeLetterhead: bool = True
    language: str = "en"

class Hl7v2ToFhirRequest(BaseModel):
    hl7Message: str

class ValidationRequest(BaseModel):
    content: str
    format: str  # FHIR_R4, C_CDA


# ── Routes ──

@router.post("/ccda-to-fhir")
async def ccda_to_fhir(
    file: UploadFile = File(...),
    validateOutput: bool = Form(True),
    current_user = Depends(get_current_active_user),
):
    """Convert C-CDA XML document to FHIR R4 Bundle."""
    content = await file.read()
    xml_str = content.decode("utf-8")

    result = conversion_service.ccda_to_fhir(xml_str)

    if validateOutput and result.success:
        validation = conversion_service.validate_fhir(result.output)
        result.validation_errors = validation.get("issues_count", 0)

    return {
        "success": result.success,
        "content": result.output,
        "format": "FHIR_R4",
        "validation_errors": result.validation_errors,
        "error_message": result.error_message,
        "metadata": {
            "converter_version": "1.0.0",
            "processing_time_ms": 0,
            "resources_converted": result.output.count('"resourceType"') if result.success else 0,
            "fhir_version": "R4",
        },
    }


@router.post("/fhir-to-ccda")
async def fhir_to_ccda(
    request: FhirToCcdaRequest,
    current_user = Depends(get_current_active_user),
):
    """Convert FHIR R4 Bundle to C-CDA XML."""
    result = conversion_service.fhir_to_ccda(request.fhirBundleJson)

    return {
        "success": result.success,
        "content": result.output,
        "format": "C_CDA",
        "error_message": result.error_message,
        "metadata": {
            "converter_version": "1.0.0",
            "fhir_version": "R4",
        },
    }


@router.post("/fhir-to-pdf")
async def fhir_to_pdf(
    request: FhirToPdfRequest,
    current_user = Depends(get_current_active_user),
):
    """Convert FHIR R4 Bundle to PDF clinical summary."""
    result = conversion_service.fhir_to_pdf(request.fhirJson)

    if result.success:
        import base64
        pdf_base64 = base64.b64encode(result.output.encode("latin-1")).decode("utf-8")

        return {
            "success": True,
            "content": pdf_base64,
            "format": "PDF",
            "metadata": {
                "converter_version": "1.0.0",
                "processing_time_ms": 0,
                "fhir_version": "R4",
            },
        }

    return {
        "success": False,
        "error_message": result.error_message,
    }


@router.post("/hl7v2-to-fhir")
async def hl7v2_to_fhir(
    request: Hl7v2ToFhirRequest,
    current_user = Depends(get_current_active_user),
):
    """Convert HL7 v2 message to FHIR R4 Bundle."""
    result = conversion_service.hl7v2_to_fhir(request.hl7Message)

    return {
        "success": result.success,
        "content": result.output,
        "format": "FHIR_R4",
        "error_message": result.error_message,
        "metadata": {
            "converter_version": "1.0.0",
            "fhir_version": "R4",
        },
    }


@router.post("/validate")
async def validate_document(
    request: ValidationRequest,
    current_user = Depends(get_current_active_user),
):
    """Validate a FHIR R4 or C-CDA document."""
    if request.format.upper() == "FHIR_R4":
        result = conversion_service.validate_fhir(request.content)
        return {
            "valid": result.get("valid", False),
            "errors": result.get("issues_count", 0),
            "warnings": result.get("warnings_count", 0),
            "issues": result.get("issues", []),
            "profile_url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient",
        }
    else:
        return {"valid": True, "errors": 0, "warnings": 0, "message": "C-CDA validation not yet implemented"}
