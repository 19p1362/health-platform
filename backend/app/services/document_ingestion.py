"""
HealthBridge Platform — Document Ingestion Service

Takes a photo/scan/PDF of a hospital document (prescription, lab report,
pharmacy bill, discharge summary) and converts it to structured
FHIR patient records via OCR + AI extraction.

Pipeline:  Upload → PDF text extraction (if PDF) or OCR (if image)
           → AI Extraction (LLM) → FHIR Bundle → Store
"""

from __future__ import annotations

import json
import logging
import time
import uuid
import re
from datetime import datetime
from io import BytesIO

from app.config import settings, DATA_DIR

logger = logging.getLogger("healthbridge.document_ingestion")

# ── Supported document types ──

DOCUMENT_TYPES = {
    "prescription": "Medical prescription with medicines, dosage, doctor notes",
    "lab_report": "Laboratory/diagnostic test report with test names and values",
    "pharmacy_bill": "Pharmacy bill/invoice with medicine names and quantities",
    "discharge_summary": "Hospital discharge summary with diagnosis, treatment, follow-up",
    "vaccination_card": "Vaccination record card",
    "general": "General medical document",
}

# ── Try importing OCR libraries (optional) ──

_HAS_OCR = False
try:
    import pytesseract
    from PIL import Image

    _HAS_OCR = True
except ImportError:
    logger.info("pytesseract/Pillow not installed — OCR disabled")


# ══════════════════════════════════════════════════════════
# OCR — Extract raw text from image
# ══════════════════════════════════════════════════════════


def ocr_image(image_bytes: bytes) -> str:
    """Run Tesseract OCR on image bytes. Returns raw text."""
    if not _HAS_OCR:
        raise RuntimeError(
            "OCR libraries not installed. Run: pip install pytesseract Pillow"
        )
    img = Image.open(BytesIO(image_bytes))
    text = pytesseract.image_to_string(img, lang="eng+hin")  # English + Hindi
    return text.strip()


# ── Try importing PDF libraries (optional) ──

_HAS_PDF_TEXT = False
_HAS_PDF_IMG = False
try:
    import pdfplumber  # text-based PDFs

    _HAS_PDF_TEXT = True
except ImportError:
    pass

try:
    from pdf2image import convert_bytes  # scanned PDFs → images

    _HAS_PDF_IMG = True
except ImportError:
    pass


# ══════════════════════════════════════════════════════════
# PDF — Extract text from PDF (typed or scanned)
# ══════════════════════════════════════════════════════════


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF.

    Strategy:
      1. Try pdfplumber for typed/text-based PDFs (fast, native text)
      2. If that yields nothing, it's a scanned PDF — convert pages
         to images and OCR each one
    """
    text = ""

    # Method 1: Text-based PDF — extract directly
    if _HAS_PDF_TEXT:
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    pages_text.append(page_text)
                text = "\n\n--- Page Break ---\n\n".join(pages_text).strip()
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")

    # If we got substantial text, return it
    if len(text) > 50:
        logger.info(f"Extracted {len(text)} chars from text-based PDF")
        return text

    # Method 2: Scanned PDF — convert to images and OCR
    if _HAS_PDF_IMG and _HAS_OCR:
        try:
            images = convert_bytes(pdf_bytes, dpi=300)
            ocr_pages = []
            for i, img in enumerate(images):
                img_bytes = BytesIO()
                img.save(img_bytes, format="PNG")
                page_text = ocr_image(img_bytes.getvalue())
                ocr_pages.append(page_text)
            text = "\n\n--- Page Break ---\n\n".join(ocr_pages).strip()
            logger.info(f"OCR extracted {len(text)} chars from scanned PDF ({len(images)} pages)")
        except Exception as e:
            logger.warning(f"Scanned PDF OCR failed: {e}")

    return text


def extract_text(data: bytes, content_type: str) -> str:
    """Route to the right text extractor based on content type."""
    if "pdf" in content_type:
        return extract_pdf_text(data)
    else:
        return ocr_image(data)


# ══════════════════════════════════════════════════════════
# AI Extraction — LLM prompt to extract structured data
# ══════════════════════════════════════════════════════════


EXTRACTION_SYSTEM_PROMPT = """You are a medical document extraction AI for Indian hospitals.
Extract structured patient data from the OCR text of a hospital document.

Return a JSON object with these fields (use null for missing):
{
  "patient": {
    "name": str or null,
    "age": int or null,
    "gender": "MALE"|"FEMALE"|"OTHER"|null,
    "phone": str or null,
    "address": str or null
  },
  "document": {
    "type": "prescription"|"lab_report"|"pharmacy_bill"|"discharge_summary"|"unknown",
    "date": "YYYY-MM-DD" or null,
    "doctor_name": str or null,
    "hospital_name": str or null,
    "hospital_address": str or null
  },
  "clinical": {
    "diagnosis": [str] or [],
    "symptoms": [str] or [],
    "vitals": [{"name": str, "value": str, "unit": str}] or [],
    "medicines": [{"name": str, "dosage": str, "frequency": str, "duration": str}] or [],
    "lab_tests": [{"name": str, "value": str, "unit": str, "reference_range": str}] or [],
    "procedures": [str] or [],
    "allergies": [str] or [],
    "follow_up": str or null
  }
}

IMPORTANT RULES:
- Extract ALL medicine names, lab values, and dosages you can find
- Use generic medicine names when possible
- For lab reports, include every test with its value and unit
- Dates are in DD/MM/YYYY or YYYY-MM-DD format — normalize to YYYY-MM-DD
- Phone numbers are 10-digit Indian mobile numbers
- If the document type is unclear, use "unknown"
- Return ONLY valid JSON, no markdown, no explanation"""


async def ai_extract(ocr_text: str, document_type_hint: str = "general") -> dict:
    """Send OCR text to LLM for structured data extraction.

    Uses the configured AI provider (OpenAI-compatible API).
    Falls back to mock extraction if no API key is configured.
    """
    import httpx

    if not settings.AI_EXTRACTION_API_KEY:
        logger.warning("No AI_EXTRACTION_API_KEY configured — using mock extraction")
        return _mock_extraction(ocr_text, document_type_hint)

    user_prompt = (
        f"Document type hint: {document_type_hint}\n\n"
        f"OCR text from medical document:\n\n{ocr_text[:8000]}"
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                settings.AI_EXTRACTION_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.AI_EXTRACTION_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.AI_EXTRACTION_MODEL,
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # Strip any markdown code fences
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(content)
    except Exception as e:
        logger.error(f"AI extraction failed: {e}")
        return _mock_extraction(ocr_text, document_type_hint)


def _mock_extraction(ocr_text: str, document_type_hint: str = "general") -> dict:
    """Fallback mock extraction when no AI API is configured.
    Uses simple keyword matching to extract some structure.
    """
    extracted: dict = {
        "patient": {"name": None, "age": None, "gender": None, "phone": None, "address": None},
        "document": {
            "type": document_type_hint if document_type_hint != "general" else "unknown",
            "date": None,
            "doctor_name": None,
            "hospital_name": None,
            "hospital_address": None,
        },
        "clinical": {
            "diagnosis": [],
            "symptoms": [],
            "vitals": [],
            "medicines": [],
            "lab_tests": [],
            "procedures": [],
            "allergies": [],
            "follow_up": None,
        },
    }

    lines = ocr_text.split("\n")
    text_lower = ocr_text.lower()

    # Try to find patient name (first non-empty line that isn't a header)
    for line in lines[:15]:
        line = line.strip()
        if line and len(line) > 3 and not any(
            h in line.lower() for h in ["hospital", "clinic", "dr.", "phone", "date", "name"]
        ):
            extracted["patient"]["name"] = line
            break

    # Try to find date
    date_patterns = [
        r"\d{2}/\d{2}/\d{4}",
        r"\d{4}-\d{2}-\d{2}",
        r"\d{2}-\d{2}-\d{4}",
    ]
    for pat in date_patterns:
        m = re.search(pat, ocr_text)
        if m:
            extracted["document"]["date"] = m.group()
            break

    # Try to find phone (Indian mobile)
    phone_m = re.search(r"(?:\+91|91)?[6-9]\d{9}", ocr_text)
    if phone_m:
        extracted["patient"]["phone"] = phone_m.group()

    # Try to find doctor name
    for line in lines:
        if "dr." in line.lower() or "dr " in line.lower():
            extracted["document"]["doctor_name"] = line.strip()
            break

    # Try to find age
    age_m = re.search(r"(\d+)\s*(?:yrs?|years?|year)", text_lower)
    if age_m:
        extracted["patient"]["age"] = int(age_m.group(1))

    # Try to find gender
    if re.search(r"\bmale\b", text_lower):
        extracted["patient"]["gender"] = "MALE"
    elif re.search(r"\bfemale\b", text_lower):
        extracted["patient"]["gender"] = "FEMALE"

    # Try to find medicines (common Indian medicine keywords)
    medicine_keywords = [
        "tablet", "tab", "capsule", "cap", "syrup", "injection", "inj",
        "cream", "ointment", "drops", "spray", "mg", "ml", "gm",
    ]
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in medicine_keywords) and len(line) > 10:
            extracted["clinical"]["medicines"].append({
                "name": line.strip(),
                "dosage": None,
                "frequency": None,
                "duration": None,
            })

    # Try to find lab test values
    lab_keywords = ["hb", "wbc", "rbc", "platelet", "glucose", "cholesterol",
                    "creatinine", "bilirubin", "sodium", "potassium", "tsh",
                    "hba1c", "hdl", "ldl", "triglycerides", "vitamin"]
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in lab_keywords):
            # Extract value + unit pattern
            vm = re.search(r"(\d+\.?\d*)\s*([a-zA-Z/%]+)", line)
            if vm:
                extracted["clinical"]["lab_tests"].append({
                    "name": line.strip().split(vm.group(0))[0].strip() or line.strip(),
                    "value": vm.group(1),
                    "unit": vm.group(2),
                    "reference_range": None,
                })

    return extracted


# ══════════════════════════════════════════════════════════
# FHIR Conversion — Extracted data → FHIR R4 Bundle
# ══════════════════════════════════════════════════════════


def extracted_to_fhir(extracted: dict, patient_id: str | None = None) -> dict:
    """Convert extracted structured data into a FHIR R4 Bundle document."""
    now = datetime.utcnow().isoformat()

    entries: list[dict] = []

    # Patient resource
    pat = extracted.get("patient", {})
    patient_resource = {
        "resourceType": "Patient",
        "id": patient_id or str(uuid.uuid4()),
        "name": [{"text": pat.get("name") or "Unknown", "given": [(pat.get("name") or "").split()[0] if pat.get("name") else "Unknown"]}],
        "gender": (pat.get("gender") or "unknown").lower(),
        "birthDate": None,
        "telecom": [{"system": "phone", "value": pat["phone"]}] if pat.get("phone") else [],
    }
    if pat.get("age"):
        from datetime import date
        birth_year = date.today().year - pat["age"]
        patient_resource["birthDate"] = f"{birth_year}-01-01"

    entries.append({
        "fullUrl": f"urn:uuid:{patient_resource['id']}",
        "resource": patient_resource,
    })

    # Condition (diagnosis)
    for dx in extracted.get("clinical", {}).get("diagnosis", []):
        entries.append({
            "fullUrl": f"urn:uuid:{uuid.uuid4()}",
            "resource": {
                "resourceType": "Condition",
                "id": str(uuid.uuid4()),
                "subject": {"reference": f"urn:uuid:{patient_resource['id']}"},
                "code": {"text": dx},
                "clinicalStatus": {"coding": [{"code": "active"}]},
            },
        })

    # Medications
    for med in extracted.get("clinical", {}).get("medicines", []):
        med_resource = {
            "resourceType": "MedicationRequest",
            "id": str(uuid.uuid4()),
            "subject": {"reference": f"urn:uuid:{patient_resource['id']}"},
            "medicationCodeableConcept": {"text": med.get("name", "Unknown")},
            "status": "active",
            "intent": "order",
        }
        dosage_text = " ".join(filter(None, [med.get("dosage"), med.get("frequency"), med.get("duration")]))
        if dosage_text:
            med_resource["dosageInstruction"] = [{"text": dosage_text}]
        entries.append({
            "fullUrl": f"urn:uuid:{med_resource['id']}",
            "resource": med_resource,
        })

    # Lab tests / Observations
    for lab in extracted.get("clinical", {}).get("lab_tests", []):
        obs_resource = {
            "resourceType": "Observation",
            "id": str(uuid.uuid4()),
            "subject": {"reference": f"urn:uuid:{patient_resource['id']}"},
            "code": {"text": lab.get("name", "Unknown test")},
            "valueQuantity": {
                "value": float(lab["value"]) if lab.get("value") else 0,
                "unit": lab.get("unit", ""),
            } if lab.get("value") else {},
            "status": "final",
        }
        if lab.get("reference_range"):
            obs_resource["referenceRange"] = [{"text": lab["reference_range"]}]
        entries.append({
            "fullUrl": f"urn:uuid:{obs_resource['id']}",
            "resource": obs_resource,
        })

    # Vital signs
    for vit in extracted.get("clinical", {}).get("vitals", []):
        entries.append({
            "fullUrl": f"urn:uuid:{uuid.uuid4()}",
            "resource": {
                "resourceType": "Observation",
                "id": str(uuid.uuid4()),
                "subject": {"reference": f"urn:uuid:{patient_resource['id']}"},
                "code": {"text": vit.get("name", "Vital")},
                "valueQuantity": {
                    "value": float(vit["value"]) if vit.get("value") else 0,
                    "unit": vit.get("unit", ""),
                } if vit.get("value") else {},
                "status": "final",
            },
        })

    # Bundle wrapper
    bundle = {
        "resourceType": "Bundle",
        "type": "document",
        "timestamp": now,
        "entry": entries,
    }

    return bundle


# ══════════════════════════════════════════════════════════
# Full Pipeline
# ══════════════════════════════════════════════════════════


async def process_document(
    image_bytes: bytes,
    filename: str = "upload.jpg",
    document_type: str = "general",
    patient_id: str | None = None,
) -> dict:
    """Run the full document ingestion pipeline.

    Steps:
    1. Save raw upload
    2. OCR → raw text
    3. AI extraction → structured JSON
    4. Convert to FHIR Bundle
    5. Return everything for storage
    """
    start = time.time()

    # 1. Save upload
    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    file_path = upload_dir / safe_name
    file_path.write_bytes(image_bytes)

    result: dict = {
        "file_path": str(file_path),
        "file_size_bytes": len(image_bytes),
        "original_filename": filename,
        "document_type": document_type,
        "source_format": "pdf" if filename.lower().endswith(".pdf") else "photo",
        "status": "PENDING",
        "ocr_text": None,
        "extracted": None,
        "fhir_bundle": None,
        "patient_id": patient_id,
        "error_message": None,
    }

    # 2. Extract text (PDF text extraction or OCR for images)
    try:
        content_type = "application/pdf" if filename.lower().endswith(".pdf") else "image/jpeg"
        raw_text = extract_text(image_bytes, content_type)
        result["ocr_text"] = raw_text
        logger.info(f"Extracted {len(raw_text)} chars from {filename}")
    except Exception as e:
        logger.warning(f"OCR failed for {filename}: {e}")
        result["error_message"] = f"OCR failed: {e}"
        result["status"] = "FAILED"
        result["processing_time_ms"] = int((time.time() - start) * 1000)
        return result

    if not raw_text.strip():
        result["error_message"] = "OCR returned empty text"
        result["status"] = "FAILED"
        result["processing_time_ms"] = int((time.time() - start) * 1000)
        return result

    # 3. AI Extraction
    try:
        extracted = await ai_extract(raw_text, document_type)
        result["extracted"] = extracted
        logger.info(f"AI extraction complete for {filename}")
    except Exception as e:
        logger.error(f"AI extraction failed for {filename}: {e}")
        result["error_message"] = f"AI extraction failed: {e}"
        result["status"] = "FAILED"
        result["processing_time_ms"] = int((time.time() - start) * 1000)
        return result

    # 4. FHIR Conversion
    try:
        fhir_bundle = extracted_to_fhir(extracted, patient_id)
        result["fhir_bundle"] = fhir_bundle
        logger.info(f"FHIR bundle created with {len(fhir_bundle.get('entry', []))} resources")
    except Exception as e:
        logger.error(f"FHIR conversion failed: {e}")
        result["error_message"] = f"FHIR conversion failed: {e}"
        result["status"] = "FAILED"
        result["processing_time_ms"] = int((time.time() - start) * 1000)
        return result

    result["status"] = "PROCESSED"
    result["processing_time_ms"] = int((time.time() - start) * 1000)

    # Extract confidence from document type match
    if extracted.get("document", {}).get("type") != "unknown":
        result["confidence_score"] = 70  # AI extraction was used
    else:
        result["confidence_score"] = 40  # Document type unclear

    return result
