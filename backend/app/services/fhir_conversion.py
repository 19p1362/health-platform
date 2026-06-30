"""
HealthBridge Platform — FHIR Conversion Service

Handles bidirectional conversion between:
  - C-CDA XML         ↔ FHIR R4 Bundle
  - HL7 v2 (pipe)     → FHIR R4 Bundle
  - FHIR R4           → PDF Clinical Summary (ReportLab)
  - FHIR R4           → Validation against core profiles

All conversions are logged to the ConversionLog table for auditability.
Provenance resources are attached to every conversion.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from io import BytesIO
from typing import Any

from app.config import settings

logger = logging.getLogger("healthbridge.fhir_conversion")

# ── Optional dependency guards ──────────────────────────────────────────────

_HAS_FHIR = False
_HAS_XML = False
_HAS_PDF = False

try:
    from fhir.resources.bundle import Bundle, BundleEntry
    from fhir.resources.patient import Patient
    from fhir.resources.observation import Observation
    from fhir.resources.condition import Condition
    from fhir.resources.medicationrequest import MedicationRequest
    from fhir.resources.diagnosticreport import DiagnosticReport
    from fhir.resources.procedure import Procedure
    from fhir.resources.encounter import Encounter
    from fhir.resources.allergyintolerance import AllergyIntolerance
    from fhir.resources.immunization import Immunization
    from fhir.resources.documentreference import DocumentReference
    from fhir.resources.provenance import Provenance, ProvenanceAgent, ProvenanceEntity
    from fhir.resources.codeableconcept import CodeableConcept
    from fhir.resources.coding import Coding
    from fhir.resources.identifier import Identifier
    from fhir.resources.humanname import HumanName
    from fhir.resources.contactpoint import ContactPoint
    from fhir.resources.reference import Reference
    from fhir.resources.period import Period
    from fhir.resources.quantity import Quantity
    from fhir.resources.meta import Meta
    from fhir.resources.attachment import Attachment
    from fhir.resources.dosage import Dosage

    _HAS_FHIR = True
except ImportError as exc:
    logger.warning("fhir.resources not available: %s", exc)

try:
    import defusedxml.ElementTree as ET

    _HAS_XML = True
except ImportError as exc:
    logger.warning("XML libraries not available: %s", exc)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable,
    )


    _HAS_PDF = True
except ImportError as exc:
    logger.warning("ReportLab not available: %s", exc)


# ═════════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════════

FHIR_VERSION = "4.0.1"

# Mapping from our record types to FHIR resource types
RECORD_TYPE_TO_FHIR = {
    "CONDITION": "Condition",
    "MEDICATION_REQUEST": "MedicationRequest",
    "MEDICATION_STATEMENT": "MedicationStatement",
    "OBSERVATION": "Observation",
    "DIAGNOSTIC_REPORT": "DiagnosticReport",
    "PROCEDURE": "Procedure",
    "ENCOUNTER": "Encounter",
    "ALLERGY_INTOLERANCE": "AllergyIntolerance",
    "IMMUNIZATION": "Immunization",
    "DOCUMENT_REFERENCE": "DocumentReference",
}

FHIR_TO_RECORD_TYPE = {v: k for k, v in RECORD_TYPE_TO_FHIR.items()}

# FHIR validation profiles (US Core / base R4)
CORE_PROFILES = {
    "Patient": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient",
    "Condition": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition",
    "Observation": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation-lab",
    "MedicationRequest": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-medicationrequest",
    "MedicationStatement": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-medicationstatement",
    "DiagnosticReport": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-diagnosticreport",
    "Procedure": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-procedure",
    "Encounter": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-encounter",
    "AllergyIntolerance": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-allergyintolerance",
    "Immunization": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-immunization",
    "DocumentReference": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-documentreference",
}

# SNOMED-CT code system URL
SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
ICD_10 = "http://hl7.org/fhir/sid/icd-10"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
UCUM = "http://unitsofmeasure.org"


# ═════════════════════════════════════════════════════════════════════════════
# Service Class
# ═════════════════════════════════════════════════════════════════════════════

class FhirConversionService:
    """FHIR conversion service for HealthBridge Platform.

    Provides bidirectional format conversion, PDF report generation,
    and FHIR validation, all with full provenance tracking and audit logging.
    """

    def __init__(self, db_session: Any | None = None):
        self.db_session = db_session
        self._conversion_id: str | None = None

    # ── Public API ───────────────────────────────────────────────────────

    def ccda_to_fhir(self, xml_str: str, patient_id: str | None = None) -> dict[str, Any]:
        """Convert C-CDA XML document to FHIR R4 Bundle.

        Args:
            xml_str: Raw C-CDA XML document text.
            patient_id: Optional patient identifier for provenance tracking.

        Returns:
            Dict with keys: 'bundle' (FHIR Bundle as dict), 'resources_converted',
            'validation_errors', 'validation_warnings', 'error_message'.
        """
        start = time.monotonic()
        result: dict[str, Any] = {
            "bundle": None,
            "resources_converted": 0,
            "validation_errors": 0,
            "validation_warnings": 0,
            "error_message": None,
        }

        if not _HAS_XML:
            result["error_message"] = "XML parsing libraries not installed"
            self._log_conversion("C_CDA", "FHIR_R4", False, start, result)
            return result

        try:
            # Parse C-CDA XML safely (defusedxml prevents XXE)
            root = ET.fromstring(xml_str.encode("utf-8"))

            # Extract clinical document header
            ns = self._ccda_namespaces(root)

            patient = self._ccda_extract_patient(root, ns)
            entries: list[Any] = []

            # Build bundle
            bundle = self._create_bundle("collection", patient_id)

            # Add Patient resource
            if patient:
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{patient.id}"
                be.resource = patient
                entries.append(be)

            # Parse each C-CDA section and convert to FHIR resources
            sections = self._ccda_get_sections(root, ns)

            # ── Problems / Conditions ──
            for cond in self._ccda_parse_conditions(sections.get("problems", [])):
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{cond.id}"
                be.resource = cond
                entries.append(be)

            # ── Medications ──
            for med_req in self._ccda_parse_medications(sections.get("medications", [])):
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{med_req.id}"
                be.resource = med_req
                entries.append(be)

            # ── Results / Observations ──
            for obs in self._ccda_parse_results(sections.get("results", [])):
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{obs.id}"
                be.resource = obs
                entries.append(be)

            # ── Vital Signs ──
            for vs in self._ccda_parse_vitals(sections.get("vitals", [])):
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{vs.id}"
                be.resource = vs
                entries.append(be)

            # ── Procedures ──
            for proc in self._ccda_parse_procedures(sections.get("procedures", [])):
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{proc.id}"
                be.resource = proc
                entries.append(be)

            # ── Encounters ──
            for enc in self._ccda_parse_encounters(sections.get("encounters", [])):
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{enc.id}"
                be.resource = enc
                entries.append(be)

            # ── Allergies ──
            for allerg in self._ccda_parse_allergies(sections.get("allergies", [])):
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{allerg.id}"
                be.resource = allerg
                entries.append(be)

            # ── Immunizations ──
            for imm in self._ccda_parse_immunizations(sections.get("immunizations", [])):
                be = BundleEntry.model_construct()
                be.fullUrl = f"urn:uuid:{imm.id}"
                be.resource = imm
                entries.append(be)

            # ── Attach provenance on each resource ──
            provenance = self._create_provenance(
                target_refs=[e.fullUrl for e in entries if e.resource is not None],
                patient_id=patient_id or "unknown",
                activity="CONVERSION",
            )
            prov_entry = BundleEntry.model_construct()
            prov_entry.fullUrl = f"urn:uuid:{provenance.id}"
            prov_entry.resource = provenance
            entries.append(prov_entry)

            bundle.entry = entries
            result["bundle"] = bundle.model_dump(mode="json")
            result["resources_converted"] = len(entries) - 1  # exclude provenance

            # Basic validation on output
            val_errors, val_warnings = self._validate_fhir_bundle(result["bundle"])
            result["validation_errors"] = val_errors
            result["validation_warnings"] = val_warnings

            self._log_conversion("C_CDA", "FHIR_R4", True, start, result)

        except ET.ParseError as exc:
            result["error_message"] = f"C-CDA XML parse error: {exc}"
            self._log_conversion("C_CDA", "FHIR_R4", False, start, result)
        except Exception as exc:
            result["error_message"] = f"C-CDA to FHIR conversion failed: {exc}"
            logger.exception("C-CDA→FHIR error")
            self._log_conversion("C_CDA", "FHIR_R4", False, start, result)

        return result

    def fhir_to_ccda(self, bundle_json: dict[str, Any]) -> dict[str, Any]:
        """Convert FHIR R4 Bundle to C-CDA XML document.

        Args:
            bundle_json: FHIR Bundle as a Python dict.

        Returns:
            Dict with keys: 'ccda_xml' (str), 'resources_converted',
            'validation_errors', 'validation_warnings', 'error_message'.
        """
        start = time.monotonic()
        result: dict[str, Any] = {
            "ccda_xml": None,
            "resources_converted": 0,
            "validation_errors": 0,
            "validation_warnings": 0,
            "error_message": None,
        }

        if not _HAS_XML:
            result["error_message"] = "XML libraries not installed"
            self._log_conversion("FHIR_R4", "C_CDA", False, start, result)
            return result

        try:
            bundle = bundle_json
            entries = bundle.get("entry", [])

            resources: dict[str, list[dict]] = {}
            for entry in entries:
                resource = entry.get("resource", {})
                rt = resource.get("resourceType", "Unknown")
                resources.setdefault(rt, []).append(resource)

            # Build C-CDA clinical document
            doc_id = str(uuid.uuid4())
            now_iso = datetime.utcnow().strftime("%Y%m%d%H%M%S")

            patient = (resources.get("Patient") or [{}])[0]
            conditions = resources.get("Condition", [])
            med_requests = resources.get("MedicationRequest", [])
            observations = resources.get("Observation", [])
            procedures = resources.get("Procedure", [])
            encounters = resources.get("Encounter", [])
            allergies = resources.get("AllergyIntolerance", [])
            immunizations = resources.get("Immunization", [])

            # Build XML manually for full control over C-CDA structure
            xml_parts: list[str] = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
                '  <realmCode code="US"/>',
                '  <typeId root="2.16.840.1.113883.1.3" extension="POCD_HD000040"/>',
                '  <templateId root="2.16.840.1.113883.10.20.22.1.1"/>',
                f'  <id root="{doc_id}"/>',
                '  <code code="34133-9" codeSystem="2.16.840.1.113883.6.1" displayName="Summarization of Episode Note"/>',
                '  <title>HealthBridge Clinical Summary</title>',
                f'  <effectiveTime value="{now_iso}"/>',
                '  <confidentialityCode code="N" codeSystem="2.16.840.1.113883.5.25"/>',
                '  <languageCode code="en-US"/>',
                self._ccda_patient_xml(patient),
                self._ccda_author_xml(),
                self._ccda_custodian_xml(),
                "  <component>",
                "    <structuredBody>",
            ]

            section_count = 0

            # ── Problems section ──
            if conditions:
                section_count += 1
                xml_parts.append(self._ccda_section_wrapper(
                    "Conditions / Problems",
                    "11450-4",
                    "Problem List",
                    conditions,
                    self._ccda_condition_entry_xml,
                ))

            # ── Medications section ──
            if med_requests:
                section_count += 1
                xml_parts.append(self._ccda_section_wrapper(
                    "Medications",
                    "10160-0",
                    "History of Medication Use",
                    med_requests,
                    self._ccda_medication_entry_xml,
                ))

            # ── Results section ──
            if observations:
                section_count += 1
                xml_parts.append(self._ccda_section_wrapper(
                    "Results",
                    "30954-2",
                    "Relevant Diagnostic Tests/Laboratory Data",
                    observations,
                    self._ccda_observation_entry_xml,
                ))

            # ── Procedures section ──
            if procedures:
                section_count += 1
                xml_parts.append(self._ccda_section_wrapper(
                    "Procedures",
                    "47519-4",
                    "History of Procedures",
                    procedures,
                    self._ccda_procedure_entry_xml,
                ))

            # ── Encounters section ──
            if encounters:
                section_count += 1
                xml_parts.append(self._ccda_section_wrapper(
                    "Encounters",
                    "46240-8",
                    "History of Encounters",
                    encounters,
                    self._ccda_encounter_entry_xml,
                ))

            # ── Allergies section ──
            if allergies:
                section_count += 1
                xml_parts.append(self._ccda_section_wrapper(
                    "Allergies",
                    "52473-6",
                    "Allergy List",
                    allergies,
                    self._ccda_allergy_entry_xml,
                ))

            # ── Immunizations section ──
            if immunizations:
                section_count += 1
                xml_parts.append(self._ccda_section_wrapper(
                    "Immunizations",
                    "11369-6",
                    "History of Immunizations",
                    immunizations,
                    self._ccda_immunization_entry_xml,
                ))

            if section_count == 0:
                xml_parts.append("      <component><section><code code="
                                 '"11368-8" codeSystem="2.16.840.1.113883.6.1" '
                                 'displayName="General"/><text>No clinical data available</text></section></component>')

            xml_parts.append("    </structuredBody>")
            xml_parts.append("  </component>")
            xml_parts.append("</ClinicalDocument>")

            ccda_xml = "\n".join(xml_parts)
            result["ccda_xml"] = ccda_xml
            result["resources_converted"] = len(entries)

            self._log_conversion("FHIR_R4", "C_CDA", True, start, result)

        except Exception as exc:
            result["error_message"] = f"FHIR → C-CDA conversion failed: {exc}"
            logger.exception("FHIR→C-CDA error")
            self._log_conversion("FHIR_R4", "C_CDA", False, start, result)

        return result

    def fhir_to_pdf(self, bundle_json: dict[str, Any]) -> dict[str, Any]:
        """Generate a PDF clinical summary from a FHIR R4 Bundle.

        Uses ReportLab to produce a formatted, paginated clinical summary
        document with patient demographics, conditions, medications,
        lab results, procedures, encounters, allergies, and immunizations.

        Args:
            bundle_json: FHIR Bundle as a Python dict.

        Returns:
            Dict with keys: 'pdf_bytes' (base64 encoded str or raw bytes),
            'resources_converted', 'error_message'.
        """
        start = time.monotonic()
        result: dict[str, Any] = {
            "pdf_bytes": None,
            "pdf_base64": None,
            "resources_converted": 0,
            "error_message": None,
        }

        if not _HAS_PDF:
            result["error_message"] = "ReportLab not installed"
            self._log_conversion("FHIR_R4", "PDF", False, start, result)
            return result

        try:
            bundle = bundle_json
            entries = bundle.get("entry", [])

            resources: dict[str, list[dict]] = {}
            for e in entries:
                res = e.get("resource", e) if isinstance(e, dict) else {}
                rt = res.get("resourceType", "Unknown")
                resources.setdefault(rt, []).append(res)

            buf = BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=A4,
                topMargin=15 * mm,
                bottomMargin=15 * mm,
                leftMargin=18 * mm,
                rightMargin=18 * mm,
                title="HealthBridge Clinical Summary",
                author="HealthBridge Platform",
            )

            styles = getSampleStyleSheet()
            styles.add(ParagraphStyle(
                name="HBTitle",
                parent=styles["Heading1"],
                fontSize=18,
                textColor=colors.HexColor("#1a237e"),
                spaceAfter=4 * mm,
            ))
            styles.add(ParagraphStyle(
                name="HBSubtitle",
                parent=styles["Heading2"],
                fontSize=14,
                textColor=colors.HexColor("#283593"),
                spaceAfter=3 * mm,
                spaceBefore=6 * mm,
            ))
            styles.add(ParagraphStyle(
                name="HBLabel",
                parent=styles["Normal"],
                fontSize=8,
                textColor=colors.HexColor("#888888"),
                spaceAfter=0,
            ))
            styles.add(ParagraphStyle(
                name="HBValue",
                parent=styles["Normal"],
                fontSize=10,
                spaceAfter=2 * mm,
            ))
            styles.add(ParagraphStyle(
                name="HBSectionHeader",
                parent=styles["Heading3"],
                fontSize=12,
                textColor=colors.HexColor("#37474f"),
                spaceBefore=5 * mm,
                spaceAfter=2 * mm,
                borderWidth=0,
                borderPadding=0,
            ))

            story: list[Any] = []

            # ── Header ──
            story.append(Paragraph("HealthBridge Clinical Summary", styles["HBTitle"]))
            story.append(Paragraph(
                f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                ParagraphStyle("HBSubDate", parent=styles["Normal"],
                               fontSize=9, textColor=colors.gray, spaceAfter=4 * mm),
            ))
            story.append(HRFlowable(
                width="100%", thickness=1, color=colors.HexColor("#1a237e"),
                spaceAfter=4 * mm,
            ))

            # ── Patient Demographics ──
            patients = resources.get("Patient", [])
            if patients:
                p = patients[0]
                story.append(Paragraph("Patient Information", styles["HBSubtitle"]))
                p_data = [
                    ["Name", self._fhir_human_name(p.get("name", [{}])[0])],
                    ["DOB", p.get("birthDate", "N/A")],
                    ["Gender", p.get("gender", "N/A")],
                    ["MRN", self._fhir_identifier_value(p.get("identifier", []), "MRN")],
                ]
                for ident in p.get("identifier", []):
                    if ident.get("type", {}).get("coding", [{}])[0].get("code") != "MRN":
                        p_data.append([
                            ident.get("type", {}).get("coding", [{}])[0].get("display", "ID"),
                            ident.get("value", "N/A"),
                        ])
                for addr in p.get("address", []):
                    line = ", ".join(filter(None, [
                        addr.get("line", [""])[0] if addr.get("line") else "",
                        addr.get("city", ""),
                        addr.get("state", ""),
                        addr.get("postalCode", ""),
                    ]))
                    if line:
                        p_data.append(["Address", line])

                p_table = Table(p_data, colWidths=[40 * mm, 120 * mm])
                p_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8eaf6")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c5cae9")),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ]))
                story.append(p_table)
                story.append(Spacer(1, 3 * mm))

            # ── Conditions ──
            conditions = resources.get("Condition", [])
            if conditions:
                story.append(Paragraph("Active Conditions / Problems", styles["HBSubtitle"]))
                for cond in conditions:
                    code = cond.get("code", {})
                    display = self._coding_display(code)
                    status = cond.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "unknown")
                    story.append(self._pdf_label_value(
                        f"{display} <i>({status})</i>",
                        cond.get("recordedDate", ""),
                        styles,
                    ))

            # ── Medications ──
            med_requests = resources.get("MedicationRequest", [])
            med_statements = resources.get("MedicationStatement", [])
            if med_requests or med_statements:
                story.append(Paragraph("Medications", styles["HBSubtitle"]))
                for mr in med_requests:
                    med = mr.get("medicationCodeableConcept", {}) or mr.get("medicationReference", {})
                    display = self._coding_display(med) or med.get("display", "Unknown")
                    dosages = mr.get("dosageInstruction", [])
                    dose_str = ""
                    if dosages:
                        d = dosages[0]
                        dose_str = d.get("text", "")
                        if not dose_str and d.get("doseAndRate"):
                            dr = d["doseAndRate"][0]
                            dose_q = dr.get("doseQuantity", {})
                            if dose_q:
                                dose_str = f"{dose_q.get('value', '')} {dose_q.get('unit', '')}"
                    story.append(self._pdf_label_value(
                        display,
                        f"Status: {mr.get('status', 'unknown')} | Dose: {dose_str or 'N/A'}",
                        styles,
                    ))
                for ms in med_statements:
                    med = ms.get("medicationCodeableConcept", {}) or ms.get("medicationReference", {})
                    display = self._coding_display(med) or med.get("display", "Unknown")
                    story.append(self._pdf_label_value(
                        display,
                        f"Status: {ms.get('status', 'unknown')}",
                        styles,
                    ))

            # ── Lab Results / Observations ──
            observations = resources.get("Observation", [])
            if observations:
                story.append(Paragraph("Laboratory Results", styles["HBSubtitle"]))
                obs_data = [["Test", "Value", "Flag", "Date"]]
                for obs in observations[:30]:  # limit display
                    code = obs.get("code", {})
                    test_name = self._coding_display(code) or code.get("text", "Unknown")
                    value = self._fhir_observation_value(obs)
                    flag = obs.get("interpretation", [{}])[0].get("coding", [{}])[0].get("code", "") if obs.get("interpretation") else ""
                    date_str = obs.get("effectiveDateTime", "")[:10]
                    obs_data.append([test_name, value, flag, date_str])

                if len(obs_data) > 1:
                    obs_table = Table(obs_data, colWidths=[65 * mm, 40 * mm, 25 * mm, 30 * mm])
                    obs_table.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("ALIGN", (1, 0), (2, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c5cae9")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]))
                    story.append(obs_table)

            # ── Diagnostic Reports ──
            diag_reports = resources.get("DiagnosticReport", [])
            if diag_reports:
                story.append(Paragraph("Diagnostic Reports", styles["HBSubtitle"]))
                for dr in diag_reports[:10]:
                    code = dr.get("code", {})
                    display = self._coding_display(code) or code.get("text", "Unknown")
                    status = dr.get("status", "unknown")
                    issued = dr.get("issued", "")[:10]
                    story.append(self._pdf_label_value(display, f"Status: {status} | Issued: {issued}", styles))

            # ── Procedures ──
            procedures = resources.get("Procedure", [])
            if procedures:
                story.append(Paragraph("Procedures", styles["HBSubtitle"]))
                for proc in procedures:
                    code = proc.get("code", {})
                    display = self._coding_display(code) or code.get("text", "Unknown")
                    perf_date = proc.get("performedDateTime", "")[:10] or proc.get("performedPeriod", {}).get("start", "")[:10]
                    story.append(self._pdf_label_value(
                        display,
                        f"Date: {perf_date or 'N/A'} | Status: {proc.get('status', 'unknown')}",
                        styles,
                    ))

            # ── Allergies ──
            allergies = resources.get("AllergyIntolerance", [])
            if allergies:
                story.append(Paragraph("Allergies & Intolerances", styles["HBSubtitle"]))
                for allerg in allergies:
                    code = allerg.get("code", {})
                    display = self._coding_display(code) or code.get("text", "Unknown")
                    reaction = ""
                    for r in allerg.get("reaction", []):
                        manifest = r.get("manifestation", [])
                        if manifest:
                            reaction = self._coding_display(manifest[0]) or manifest[0].get("text", "")
                    severity = allerg.get("criticality", "unknown")
                    story.append(self._pdf_label_value(
                        f"{display} <i>({severity})</i>",
                        f"Reaction: {reaction}",
                        styles,
                    ))

            # ── Immunizations ──
            immunizations = resources.get("Immunization", [])
            if immunizations:
                story.append(Paragraph("Immunizations", styles["HBSubtitle"]))
                for imm in immunizations:
                    vaccine = imm.get("vaccineCode", {})
                    display = self._coding_display(vaccine) or vaccine.get("text", "Unknown")
                    occ_date = imm.get("occurrenceDateTime", "")[:10]
                    story.append(self._pdf_label_value(
                        display,
                        f"Date: {occ_date} | Status: {imm.get('status', 'unknown')}",
                        styles,
                    ))

            # ── Footer ──
            story.append(Spacer(1, 6 * mm))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray, spaceAfter=2 * mm))
            footer_style = ParagraphStyle(
                "Footer", parent=styles["Normal"], fontSize=7,
                textColor=colors.gray, alignment=TA_CENTER,
            )
            story.append(Paragraph(
                f"HealthBridge Platform v{settings.APP_VERSION} — "
                f"DPDP 2025 Compliant — Generated {datetime.utcnow().isoformat()} UTC",
                footer_style,
            ))

            doc.build(story)
            pdf_bytes = buf.getvalue()

            result["pdf_bytes"] = pdf_bytes
            result["resources_converted"] = len(entries)
            self._log_conversion("FHIR_R4", "PDF", True, start, result)

        except Exception as exc:
            result["error_message"] = f"FHIR → PDF generation failed: {exc}"
            logger.exception("FHIR→PDF error")
            self._log_conversion("FHIR_R4", "PDF", False, start, result)

        return result

    def hl7v2_to_fhir(self, hl7_str: str, patient_id: str | None = None) -> dict[str, Any]:
        """Convert HL7 v2 pipe-delimited message to FHIR R4 Bundle.

        Supports the following HL7 v2 message types:
          - ADT^A01, ADT^A04, ADT^A08 (admit/registration/update) → Patient, Encounter
          - ORU^R01 (lab results) → Observation, DiagnosticReport
          - RDE^O11 (pharmacy order) → MedicationRequest
          - SIU^S12 (appointment) → Encounter
          - VXU^V04 (immunization) → Immunization
          - MDM^T02 (document) → DocumentReference

        Args:
            hl7_str: Pipe-delimited HL7 v2 message text.
            patient_id: Optional patient identifier for provenance.

        Returns:
            Dict with keys: 'bundle', 'resources_converted',
            'validation_errors', 'validation_warnings', 'error_message'.
        """
        start = time.monotonic()
        result: dict[str, Any] = {
            "bundle": None,
            "resources_converted": 0,
            "validation_errors": 0,
            "validation_warnings": 0,
            "error_message": None,
        }

        if not _HAS_FHIR:
            result["error_message"] = "FHIR library not installed"
            self._log_conversion("HL7_V2", "FHIR_R4", False, start, result)
            return result

        try:
            # Parse HL7 v2 segments
            segments = self._hl7_parse_segments(hl7_str)
            if not segments:
                result["error_message"] = "Empty or invalid HL7 v2 message"
                self._log_conversion("HL7_V2", "FHIR_R4", False, start, result)
                return result

            msh = segments.get("MSH", [None])[0]
            if not msh:
                result["error_message"] = "No MSH segment found"
                self._log_conversion("HL7_V2", "FHIR_R4", False, start, result)
                return result

            message_type = msh.get("fields", {}).get("8", "")  # MSH-9 in HL7 (0-indexed part 8)

            bundle = self._create_bundle("collection", patient_id)
            entries: list[Any] = []

            # Process based on message type
            mt_upper = message_type.upper().replace(" ", "")

            # ── ADT messages ──
            if "ADT" in mt_upper:
                patient = self._hl7_adt_patient(segments)
                if patient:
                    be = BundleEntry.model_construct()
                    be.fullUrl = f"urn:uuid:{patient.id}"
                    be.resource = patient
                    entries.append(be)

                encounter = self._hl7_adt_encounter(segments)
                if encounter:
                    be = BundleEntry.model_construct()
                    be.fullUrl = f"urn:uuid:{encounter.id}"
                    be.resource = encounter
                    entries.append(be)

            # ── ORU (lab results) ──
            if "ORU" in mt_upper or "ORU^R01" in mt_upper:
                obs_list = self._hl7_oru_observations(segments)
                for obs in obs_list:
                    be = BundleEntry.model_construct()
                    be.fullUrl = f"urn:uuid:{obs.id}"
                    be.resource = obs
                    entries.append(be)

                dr = self._hl7_oru_diagnostic_report(segments, obs_list)
                if dr:
                    be = BundleEntry.model_construct()
                    be.fullUrl = f"urn:uuid:{dr.id}"
                    be.resource = dr
                    entries.append(be)

            # ── RDE (pharmacy) ──
            if "RDE" in mt_upper or "RDE^O11" in mt_upper:
                med_req = self._hl7_rde_medication_request(segments)
                if med_req:
                    be = BundleEntry.model_construct()
                    be.fullUrl = f"urn:uuid:{med_req.id}"
                    be.resource = med_req
                    entries.append(be)

            # ── SIU (appointment) ──
            if "SIU" in mt_upper:
                encounter = self._hl7_siu_encounter(segments)
                if encounter:
                    be = BundleEntry.model_construct()
                    be.fullUrl = f"urn:uuid:{encounter.id}"
                    be.resource = encounter
                    entries.append(be)

            # ── VXU (immunization) ──
            if "VXU" in mt_upper or "V04" in mt_upper:
                imm = self._hl7_vxu_immunization(segments)
                if imm:
                    be = BundleEntry.model_construct()
                    be.fullUrl = f"urn:uuid:{imm.id}"
                    be.resource = imm
                    entries.append(be)

            # ── MDM (document) ──
            if "MDM" in mt_upper:
                doc_ref = self._hl7_mdm_document(segments)
                if doc_ref:
                    be = BundleEntry.model_construct()
                    be.fullUrl = f"urn:uuid:{doc_ref.id}"
                    be.resource = doc_ref
                    entries.append(be)

            # Attach provenance
            if entries:
                provenance = self._create_provenance(
                    target_refs=[e.fullUrl for e in entries],
                    patient_id=patient_id or msh.get("fields", {}).get("6", "unknown"),
                    activity="HL7_V2_CONVERSION",
                )
                prov_entry = BundleEntry.model_construct()
                prov_entry.fullUrl = f"urn:uuid:{provenance.id}"
                prov_entry.resource = provenance
                entries.append(prov_entry)

            if not entries:
                result["error_message"] = (
                    f"Unsupported HL7 v2 message type '{message_type}'. "
                    f"Supported: ADT, ORU, RDE, SIU, VXU, MDM"
                )
                self._log_conversion("HL7_V2", "FHIR_R4", False, start, result)
                return result

            bundle.entry = entries
            result["bundle"] = bundle.model_dump(mode="json")
            result["resources_converted"] = len(entries) - 1

            val_errors, val_warnings = self._validate_fhir_bundle(result["bundle"])
            result["validation_errors"] = val_errors
            result["validation_warnings"] = val_warnings

            self._log_conversion("HL7_V2", "FHIR_R4", True, start, result)

        except Exception as exc:
            result["error_message"] = f"HL7 v2 → FHIR conversion failed: {exc}"
            logger.exception("HL7v2→FHIR error")
            self._log_conversion("HL7_V2", "FHIR_R4", False, start, result)

        return result

    def build_fhir_bundle_from_record(self, record: Any) -> str | None:
        """Build a FHIR Bundle JSON string from a PatientRecord.

        Creates a minimal FHIR Bundle with a single resource entry
        using the record's stored fhir_resource_json or constructed data.

        Args:
            record: A PatientRecord ORM instance.

        Returns:
            JSON string of a FHIR Bundle, or None if the record has no data.
        """
        import json

        resource_type = record.fhir_resource_type or "Observation"
        resource_id = record.id

        resource = {
            "resourceType": resource_type,
            "id": resource_id,
            "subject": {"reference": f"Patient/{record.patient_id}"},
            "code": {
                "coding": [
                    {
                        "system": record.code_system or "",
                        "code": record.code or "",
                    }
                ],
                "text": record.display_name or "",
            },
            "status": "final",
        }

        if record.recorded_date:
            date_str = record.recorded_date.isoformat() if hasattr(record.recorded_date, "isoformat") else str(record.recorded_date)
            resource["recordedDate"] = date_str

        bundle = {
            "resourceType": "Bundle",
            "id": str(uuid.uuid4()),
            "type": "collection",
            "entry": [
                {
                    "fullUrl": f"urn:uuid:{resource_id}",
                    "resource": resource,
                }
            ],
        }

        return json.dumps(bundle)

    def validate_fhir(self, bundle_json: dict[str, Any]) -> dict[str, Any]:
        """Validate FHIR R4 Bundle against core profiles.

        Performs structural validation (required fields, cardinality)
        and profile conformance checks for US Core profiles.

        Args:
            bundle_json: FHIR Bundle as a Python dict.

        Returns:
            Dict with keys: 'valid' (bool), 'errors' (list of str),
            'warnings' (list of str), 'resources_validated' (int).
        """
        start = time.monotonic()
        result: dict[str, Any] = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "resources_validated": 0,
        }

        if not _HAS_FHIR:
            result["valid"] = False
            result["errors"].append("FHIR library not installed")
            self._log_conversion("FHIR_R4", "FHIR_R4", False, start, result)
            return result

        try:
            entries = bundle_json.get("entry", [])
            result["resources_validated"] = len(entries)

            for entry in entries:
                resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
                resource_type = resource.get("resourceType", "Unknown")

                if resource_type == "Bundle":
                    continue

                self._validate_resource_required_fields(resource, resource_type, result)

                # Check profile conformance
                profile_url = CORE_PROFILES.get(resource_type)
                if profile_url:
                    meta = resource.get("meta", {})
                    profiles = meta.get("profile", [])
                    if profile_url not in profiles:
                        result["warnings"].append(
                            f"{resource.get('id', '?')}: Missing profile '{profile_url}' "
                            f"on {resource_type}"
                        )

            # Check bundle structure
            bundle_type = bundle_json.get("type")
            if not bundle_type:
                result["errors"].append("Bundle is missing required 'type' field")
            if bundle_type not in ("document", "collection", "batch", "transaction", "history", "searchset", "message"):
                result["warnings"].append(f"Bundle type '{bundle_type}' may not be standard")

            result["valid"] = len(result["errors"]) == 0

            self._log_conversion(
                "FHIR_R4", "FHIR_R4",
                result["valid"],
                start,
                {
                    "validation_errors": len(result["errors"]),
                    "validation_warnings": len(result["warnings"]),
                    "resources_converted": result["resources_validated"],
                },
            )

        except Exception as exc:
            result["valid"] = False
            result["errors"].append(f"Validation error: {exc}")
            self._log_conversion("FHIR_R4", "FHIR_R4", False, start, result)

        return result

    # ══════════════════════════════════════════════════════════════════════
    # Private: FHIR Bundle Creation
    # ══════════════════════════════════════════════════════════════════════

    def _create_bundle(self, bundle_type: str = "collection",
                       patient_id: str | None = None) -> Bundle:
        """Create a FHIR R4 Bundle with metadata."""
        now_ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        bundle = Bundle.model_construct(
            id=str(uuid.uuid4()),
            type=bundle_type,
            timestamp=now_ts,
            meta=Meta.model_construct(
                lastUpdated=now_ts,
                profile=["http://hl7.org/fhir/StructureDefinition/Bundle"],
            ),
        )
        return bundle

    def _create_provenance(
        self,
        target_refs: list[str],
        patient_id: str,
        activity: str = "CONVERSION",
        system: str = "HealthBridge",
    ) -> Provenance:
        """Create a FHIR Provenance resource tracking the conversion event."""
        prov = Provenance.model_construct()
        prov.id = str(uuid.uuid4())

        # Timestamp
        prov.recorded = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        # Activity (what was done)
        prov.activity = CodeableConcept.model_construct()
        prov.activity.coding = [
            Coding.model_construct(
                system="http://terminology.hl7.org/CodeSystem/v3-DataOperation",
                code="TRANSFORM",
                display="Transform",
            )
        ]

        # Agent (who did it - the HealthBridge platform)
        agent = ProvenanceAgent.model_construct()
        agent.type = CodeableConcept.model_construct()
        agent.type.coding = [
            Coding.model_construct(
                system="http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                code="author",
                display="Author",
            )
        ]
        agent.who = Reference.model_construct()
        agent.who.reference = "Organization/healthbridge-platform"
        agent.who.display = system
        prov.agent = [agent]

        # Entity (what resources were involved)
        entities: list[Any] = []
        for ref in target_refs:
            if ref:
                entity = ProvenanceEntity.model_construct()
                entity.role = "source"
                entity.what = Reference.model_construct()
                entity.what.reference = ref
                entities.append(entity)
        if entities:
            prov.entity = entities

        # Target (the output resources - same as entities for transform)
        prov.target = [Reference.model_construct(reference=r) for r in target_refs if r]

        return prov

    # ══════════════════════════════════════════════════════════════════════
    # Private: C-CDA Parsing Helpers
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _ccda_namespaces(root: Any) -> dict[str, str]:
        """Extract XML namespaces from the C-CDA document root."""
        ns = {}
        for key, value in root.attrib.items():
            if key.startswith("xmlns"):
                prefix = key.split(":")[1] if ":" in key else "default"
                ns[prefix] = value
        if "default" not in ns:
            # Try to find the default namespace
            for event, elem in ET.iterparse(BytesIO(ET.tostring(root)), events=("start",)):
                if "}" in elem.tag:
                    default_ns = elem.tag.split("}")[0].lstrip("{")
                    ns["default"] = default_ns
                    break
                break
        return ns

    @staticmethod
    def _ccda_get_sections(root: Any,
                           ns: dict[str, str]) -> dict[str, list[Any]]:
        """Extract clinical sections from C-CDA document by their LOINC codes."""
        sections: dict[str, list[Any]] = {
            "problems": [],
            "medications": [],
            "results": [],
            "vitals": [],
            "procedures": [],
            "encounters": [],
            "allergies": [],
            "immunizations": [],
        }

        # Gather raw section elements using multiple lookup strategies
        ns_val = ns.get("default", "urn:hl7-org:v3")
        sections_raw: list[Any] = []

        # Strategy 1: structuredBody → component → section
        structured_body = root.find(f".//{{{ns_val}}}structuredBody")
        if structured_body is not None:
            for comp in structured_body.findall(f"{{{ns_val}}}component"):
                section = comp.find(f"{{{ns_val}}}section")
                if section is not None:
                    sections_raw.append(section)

        # Strategy 2: component/section at top level
        if not sections_raw:
            for comp in root.findall(f".//{{{ns_val}}}component/{{{ns_val}}}section"):
                sections_raw.append(comp)

        # Strategy 3: direct section elements anywhere
        if not sections_raw:
            sections_raw = root.findall(f".//{{{ns_val}}}section")

        section_map = {
            "11450-4": "problems",
            "10160-0": "medications",
            "30954-2": "results",
            "8716-3": "vitals",
            "47519-4": "procedures",
            "46240-8": "encounters",
            "52473-6": "allergies",
            "11369-6": "immunizations",
        }

        for sec in sections_raw:
            code_elem = sec.find(
                "{%s}code" % ns.get("default", "urn:hl7-org:v3")
            )
            if code_elem is not None:
                loinc_code = code_elem.get("code", "")
                section_key = section_map.get(loinc_code)
                if section_key is not None:
                    sections[section_key].append(sec)

        return sections

    def _ccda_extract_patient(self, root: Any,
                              ns: dict[str, str]) -> Patient | None:
        """Extract Patient resource from C-CDA recordTarget."""
        try:
            ns_val = ns.get("default", "urn:hl7-org:v3")
            record_target = root.find(f".//{{{ns_val}}}recordTarget/{{{ns_val}}}patientRole")
            if record_target is None:
                return None

            patient = Patient.model_construct()
            patient.id = str(uuid.uuid4())
            patient.active = True

            # Identifiers
            ids = []
            for id_elem in record_target.findall(f"{{{ns_val}}}id"):
                ext = id_elem.get("extension", "")
                root_val = id_elem.get("root", "")
                if ext:
                    identifier = Identifier.model_construct()
                    identifier.system = f"urn:oid:{root_val}" if root_val else "urn:oid:unknown"
                    identifier.value = ext
                    ids.append(identifier)
            if ids:
                patient.identifier = ids

            # Patient person info
            patient_person = record_target.find(f"{{{ns_val}}}patient")
            if patient_person is not None:
                # Name
                name_elem = patient_person.find(f"{{{ns_val}}}name")
                if name_elem is not None:
                    hn = HumanName.model_construct()
                    given = name_elem.findtext(f"{{{ns_val}}}given", "")
                    family = name_elem.findtext(f"{{{ns_val}}}family", "")
                    hn.given = [given] if given else None
                    hn.family = family if family else None
                    hn.use = "official"
                    patient.name = [hn]

                # Gender
                gender_code = patient_person.findtext(f"{{{ns_val}}}administrativeGenderCode", "")
                gender_map = {"M": "male", "F": "female", "UN": "unknown"}
                patient.gender = gender_map.get(gender_code, "unknown")

                # DOB
                birth_time = patient_person.find(f"{{{ns_val}}}birthTime")
                if birth_time is not None:
                    patient.birthDate = self._ccda_to_date(birth_time.get("value", ""))

            # Address
            for addr_elem in record_target.findall(f"{{{ns_val}}}addr"):
                city = addr_elem.findtext(f"{{{ns_val}}}city", "")
                state = addr_elem.findtext(f"{{{ns_val}}}state", "")
                line_parts = []
                for part in addr_elem:
                    tag = part.tag.split("}")[-1] if "}" in part.tag else part.tag
                    if tag in ("streetAddressLine", "street"):
                        line_parts.append(part.text or "")
                if line_parts or city or state:
                    from fhir.resources.address import Address
                    addr = Address.model_construct()
                    if line_parts:
                        addr.line = line_parts
                    if city:
                        addr.city = city
                    if state:
                        addr.state = state
                    patient.address = [addr]
                break  # Only first address

            # Contact
            for telecom in record_target.findall(f"{{{ns_val}}}telecom"):
                value = telecom.get("value", "")
                use = telecom.get("use", "")
                if value.startswith("tel:"):
                    ct = ContactPoint.model_construct()
                    ct.system = "phone"
                    ct.value = value.replace("tel:", "")
                    ct.use = "home" if use == "H" else "work"
                    patient.telecom = [ct]
                elif value.startswith("mailto:"):
                    ct = ContactPoint.model_construct()
                    ct.system = "email"
                    ct.value = value.replace("mailto:", "")
                    patient.telecom = patient.telecom or []
                    patient.telecom.append(ct)

            return patient

        except Exception as exc:
            logger.warning("Failed to extract patient from C-CDA: %s", exc)
            return None

    def _ccda_parse_conditions(self, sections: list[Any]) -> list[Condition]:
        """Parse C-CDA Problem section entries into Condition resources."""
        conditions: list[Condition] = []
        try:
            ns = "urn:hl7-org:v3"
            for section in sections:
                entries = section.findall(f"{{{ns}}}entry")
                for entry in entries:
                    act = entry.find(f"{{{ns}}}act")
                    if act is None:
                        act = entry.find(f"{{{ns}}}observation")
                    if act is None:
                        continue

                    cond = Condition.model_construct()
                    cond.id = str(uuid.uuid4())
                    cond.subject = Reference.model_construct(reference="urn:uuid:placeholder")
                    cond.recordedDate = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

                    # Get code
                    code_elem = act.find(f"{{{ns}}}code")
                    if code_elem is not None:
                        code = self._ccda_code_from_element(code_elem, ns)
                        if code:
                            cond.code = code

                    # Status
                    status_code = act.find(f"{{{ns}}}statusCode")
                    if status_code is not None:
                        sc = status_code.get("code", "active")
                        status_map = {
                            "active": "active", "completed": "resolved",
                            "aborted": "inactive", "suspended": "inactive",
                        }
                        cond.clinicalStatus = CodeableConcept.model_construct()
                        cond.clinicalStatus.coding = [
                            Coding.model_construct(
                                system="http://terminology.hl7.org/CodeSystem/condition-clinical",
                                code=status_map.get(sc, "active"),
                            )
                        ]

                    # Effective time
                    eff_time = act.find(f"{{{ns}}}effectiveTime")
                    if eff_time is not None:
                        low = eff_time.find(f"{{{ns}}}low")
                        if low is not None:
                            cond.onsetDateTime = self._ccda_to_datetime(low.get("value", ""))

                    conditions.append(cond)

        except Exception as exc:
            logger.warning("Error parsing C-CDA conditions: %s", exc)

        return conditions

    def _ccda_parse_medications(self, sections: list[Any]) -> list[MedicationRequest]:
        """Parse C-CDA Medications section into MedicationRequest resources."""
        meds: list[MedicationRequest] = []
        try:
            ns = "urn:hl7-org:v3"
            for section in sections:
                entries = section.findall(f"{{{ns}}}entry")
                for entry in entries:
                    substance = entry.find(f"{{{ns}}}substanceAdministration")
                    if substance is None:
                        continue

                    mr = MedicationRequest.model_construct()
                    mr.id = str(uuid.uuid4())
                    mr.status = "active"
                    mr.intent = "order"
                    mr.subject = Reference.model_construct(reference="urn:uuid:placeholder")

                    # Medication code
                    consumable = substance.find(f"{{{ns}}}consumable/{{{ns}}}manufacturedProduct/{{{ns}}}manufacturedMaterial")
                    if consumable is not None:
                        code_elem = consumable.find(f"{{{ns}}}code")
                        if code_elem is not None:
                            cc = self._ccda_code_from_element(code_elem, ns)
                            if cc:
                                mr.medicationCodeableConcept = cc

                    # Dosage
                    dose_qty = substance.find(f"{{{ns}}}doseQuantity")
                    if dose_qty is not None:
                        value = dose_qty.get("value")
                        unit = dose_qty.get("unit", "")
                        if value:
                            from fhir.resources.dosage import Dosage, DosageDoseAndRate
                            dosage = Dosage.model_construct()
                            dar = DosageDoseAndRate.model_construct()
                            dar.doseQuantity = Quantity.model_construct(
                                value=float(value) if "." in value else int(value),
                                unit=unit or None,
                                system=UCUM,
                            )
                            dosage.doseAndRate = [dar]

                            # Route
                            route = substance.find(f"{{{ns}}}routeCode")
                            if route is not None:
                                dosage.route = CodeableConcept.model_construct()
                                dosage.route.coding = [
                                    Coding.model_construct(
                                        code=route.get("code", ""),
                                        display=route.get("displayName", ""),
                                    )
                                ]

                            mr.dosageInstruction = [dosage]

                    # Timing
                    eff_time = substance.find(f"{{{ns}}}effectiveTime")
                    if eff_time is not None:
                        low = eff_time.find(f"{{{ns}}}low")
                        if low is not None:
                            mr.authoredOn = low.get("value", "")[:10]

                    meds.append(mr)

        except Exception as exc:
            logger.warning("Error parsing C-CDA medications: %s", exc)

        return meds

    def _ccda_parse_results(self, sections: list[Any]) -> list[Observation]:
        """Parse C-CDA Results section into Observation resources."""
        obs_list: list[Observation] = []
        try:
            ns = "urn:hl7-org:v3"
            for section in sections:
                entries = section.findall(f"{{{ns}}}entry")
                for entry in entries:
                    obs_elem = entry.find(f"{{{ns}}}observation")
                    if obs_elem is None:
                        continue

                    obs = Observation.model_construct()
                    obs.id = str(uuid.uuid4())
                    obs.status = "final"
                    obs.subject = Reference.model_construct(reference="urn:uuid:placeholder")

                    # Code
                    code_elem = obs_elem.find(f"{{{ns}}}code")
                    if code_elem is not None:
                        obs.code = self._ccda_code_from_element(code_elem, ns)

                    # Value
                    value_elem = obs_elem.find(f"{{{ns}}}value")
                    if value_elem is not None:
                        value_type = value_elem.tag.split("}")[-1] if "}" in value_elem.tag else value_elem.tag
                        if value_type in ("PQ", "value"):
                            obs.valueQuantity = Quantity.model_construct(
                                value=float(value_elem.get("value", 0)),
                                unit=value_elem.get("unit", ""),
                            )
                        elif value_type == "ST":
                            obs.valueString = value_elem.text or value_elem.get("value", "")
                        elif value_type == "CD":
                            obs.valueCodeableConcept = self._ccda_code_from_element(value_elem, ns)

                    # Effective time
                    eff_time = obs_elem.find(f"{{{ns}}}effectiveTime")
                    if eff_time is not None:
                        obs.effectiveDateTime = eff_time.get("value", "")[:19] or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

                    # Interpretation
                    intp = obs_elem.find(f"{{{ns}}}interpretationCode")
                    if intp is not None:
                        obs.interpretation = [
                            CodeableConcept.model_construct(
                                coding=[Coding.model_construct(
                                    code=intp.get("code", ""),
                                    display=intp.get("displayName", ""),
                                )]
                            )
                        ]

                    # Reference range
                    ref_range = obs_elem.find(f"{{{ns}}}referenceRange/{{{ns}}}observationRange")
                    if ref_range is not None:
                        low = ref_range.find(f"{{{ns}}}low")
                        high = ref_range.find(f"{{{ns}}}high")
                        if low is not None or high is not None:
                            from fhir.resources.observation import ObservationReferenceRange
                            rr = ObservationReferenceRange.model_construct()
                            if low is not None:
                                rr.low = Quantity.model_construct(
                                    value=float(low.get("value", 0)),
                                    unit=low.get("unit", ""),
                                )
                            if high is not None:
                                rr.high = Quantity.model_construct(
                                    value=float(high.get("value", 0)),
                                    unit=high.get("unit", ""),
                                )
                            obs.referenceRange = [rr]

                    obs_list.append(obs)

        except Exception as exc:
            logger.warning("Error parsing C-CDA results: %s", exc)

        return obs_list

    def _ccda_parse_vitals(self, sections: list[Any]) -> list[Observation]:
        """Parse C-CDA Vital Signs section into Observation resources."""
        return self._ccda_parse_results(sections)  # Same structure

    def _ccda_parse_procedures(self, sections: list[Any]) -> list[Procedure]:
        """Parse C-CDA Procedures section into Procedure resources."""
        procs: list[Procedure] = []
        try:
            ns = "urn:hl7-org:v3"
            for section in sections:
                entries = section.findall(f"{{{ns}}}entry")
                for entry in entries:
                    proc_elem = entry.find(f"{{{ns}}}procedure")
                    if proc_elem is None:
                        proc_elem = entry.find(f"{{{ns}}}act")
                    if proc_elem is None:
                        continue

                    proc = Procedure.model_construct()
                    proc.id = str(uuid.uuid4())
                    proc.status = "completed"
                    proc.subject = Reference.model_construct(reference="urn:uuid:placeholder")

                    # Code
                    code_elem = proc_elem.find(f"{{{ns}}}code")
                    if code_elem is not None:
                        proc.code = self._ccda_code_from_element(code_elem, ns)

                    # Effective time
                    eff_time = proc_elem.find(f"{{{ns}}}effectiveTime")
                    if eff_time is not None:
                        low = eff_time.find(f"{{{ns}}}low")
                        if low is not None:
                            proc.performedDateTime = low.get("value", "")[:10]

                    procs.append(proc)

        except Exception as exc:
            logger.warning("Error parsing C-CDA procedures: %s", exc)

        return procs

    def _ccda_parse_encounters(self, sections: list[Any]) -> list[Encounter]:
        """Parse C-CDA Encounters section into Encounter resources."""
        encs: list[Encounter] = []
        try:
            ns = "urn:hl7-org:v3"
            for section in sections:
                entries = section.findall(f"{{{ns}}}entry")
                for entry in entries:
                    enc_elem = entry.find(f"{{{ns}}}encounter")
                    if enc_elem is None:
                        continue

                    enc = Encounter.model_construct()
                    enc.id = str(uuid.uuid4())
                    enc.status = "finished"
                    enc.subject = Reference.model_construct(reference="urn:uuid:placeholder")

                    # Class
                    class_code = enc_elem.find(f"{{{ns}}}code")
                    if class_code is not None:
                        enc.type = [self._ccda_code_from_element(class_code, ns)]

                    # Effective time
                    eff_time = enc_elem.find(f"{{{ns}}}effectiveTime")
                    if eff_time is not None:
                        low = eff_time.find(f"{{{ns}}}low")
                        high = eff_time.find(f"{{{ns}}}high")
                        if low is not None:
                            enc.period = Period.model_construct(
                                start=low.get("value", "")[:19],
                            )
                            if high is not None:
                                enc.period.end = high.get("value", "")[:19]

                    encs.append(enc)

        except Exception as exc:
            logger.warning("Error parsing C-CDA encounters: %s", exc)

        return encs

    def _ccda_parse_allergies(self, sections: list[Any]) -> list[AllergyIntolerance]:
        """Parse C-CDA Allergies section into AllergyIntolerance resources."""
        allergies: list[AllergyIntolerance] = []
        try:
            ns = "urn:hl7-org:v3"
            for section in sections:
                entries = section.findall(f"{{{ns}}}entry")
                for entry in entries:
                    act = entry.find(f"{{{ns}}}act")
                    if act is None:
                        continue

                    allerg = AllergyIntolerance.model_construct()
                    allerg.id = str(uuid.uuid4())
                    allerg.patient = Reference.model_construct(reference="urn:uuid:placeholder")

                    # Code (the allergen)
                    code_elem = act.find(f"{{{ns}}}code")
                    if code_elem is not None:
                        allerg.code = self._ccda_code_from_element(code_elem, ns)

                    # Severity
                    severity_elem = act.find(f"{{{ns}}}severity")
                    if severity_elem is not None:
                        sev = severity_elem.get("code", "")
                        sev_map = {
                            "SEV": "severe",
                            "MOD": "moderate",
                            "MILD": "mild",
                        }
                        allerg.criticality = sev_map.get(sev, "unable-to-assess")

                    # Reaction
                    reaction_elem = act.find(f"{{{ns}}}entryRelationship/{{{ns}}}observation")
                    if reaction_elem is not None:
                        manifestation = reaction_elem.find(f"{{{ns}}}value")
                        if manifestation is not None:
                            from fhir.resources.allergyintolerance import (
                                AllergyIntoleranceReaction,
                            )
                            rxn = AllergyIntoleranceReaction.model_construct()
                            rxn.manifestation = [
                                CodeableConcept.model_construct(
                                    coding=[Coding.model_construct(
                                        code=manifestation.get("code", ""),
                                        display=manifestation.get("displayName", ""),
                                    )]
                                )
                            ]
                            allerg.reaction = [rxn]

                    allergies.append(allerg)

        except Exception as exc:
            logger.warning("Error parsing C-CDA allergies: %s", exc)

        return allergies

    def _ccda_parse_immunizations(self, sections: list[Any]) -> list[Immunization]:
        """Parse C-CDA Immunizations section into Immunization resources."""
        immunizations: list[Immunization] = []
        try:
            ns = "urn:hl7-org:v3"
            for section in sections:
                entries = section.findall(f"{{{ns}}}entry")
                for entry in entries:
                    sub_admin = entry.find(f"{{{ns}}}substanceAdministration")
                    if sub_admin is None:
                        continue

                    imm = Immunization.model_construct()
                    imm.id = str(uuid.uuid4())
                    imm.status = "completed"
                    imm.patient = Reference.model_construct(reference="urn:uuid:placeholder")

                    # Vaccine code
                    consumable = sub_admin.find(
                        f"{{{ns}}}consumable/{{{ns}}}manufacturedProduct/"
                        f"{{{ns}}}manufacturedMaterial/{{{ns}}}code"
                    )
                    if consumable is not None:
                        imm.vaccineCode = self._ccda_code_from_element(consumable, ns)

                    # Occurrence date
                    eff_time = sub_admin.find(f"{{{ns}}}effectiveTime")
                    if eff_time is not None:
                        center = eff_time.find(f"{{{ns}}}center")
                        if center is not None:
                            imm.occurrenceDateTime = center.get("value", "")[:10]
                        else:
                            imm.occurrenceDateTime = eff_time.get("value", "")[:10]

                    immunizations.append(imm)

        except Exception as exc:
            logger.warning("Error parsing C-CDA immunizations: %s", exc)

        return immunizations

    @staticmethod
    def _ccda_code_from_element(elem: Any,
                                 ns: str = "urn:hl7-org:v3") -> CodeableConcept:
        """Extract a CodeableConcept from a C-CDA code element."""
        cc = CodeableConcept.model_construct()
        coding = Coding.model_construct()
        coding.code = elem.get("code", "")
        coding.display = elem.get("displayName", "")

        # Map OID to known system
        code_system = elem.get("codeSystem", "")
        coding.system = _ccda_oid_to_system(code_system)

        # Try to find translations
        translations = elem.findall(f"{{{ns}}}translation")
        all_codings = [coding]
        for trans in translations:
            tc = Coding.model_construct()
            tc.code = trans.get("code", "")
            tc.display = trans.get("displayName", "")
            tc.system = _ccda_oid_to_system(trans.get("codeSystem", ""))
            all_codings.append(tc)

        cc.coding = all_codings
        cc.text = elem.get("displayName", coding.code)
        return cc

    # ══════════════════════════════════════════════════════════════════════
    # Private: C-CDA Generation Helpers
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _ccda_patient_xml(patient: dict[str, Any]) -> str:
        """Generate C-CDA recordTarget XML from FHIR Patient dict."""
        name = patient.get("name", [{}])[0]
        given = (name.get("given", [""])[0] if isinstance(name.get("given"), list)
                 else name.get("given", ""))
        family = name.get("family", "")
        gender = patient.get("gender", "UN")
        gender_map = {"male": "M", "female": "F", "other": "UN", "unknown": "UN"}
        birth_date = patient.get("birthDate", "")
        mrn = ""
        for ident in patient.get("identifier", []):
            if any(c.get("code") == "MRN" for c in ident.get("type", {}).get("coding", [])):
                mrn = ident.get("value", "")
                break

        telecom_xml = ""
        for telecom in patient.get("telecom", []):
            sys = telecom.get("system", "")
            val = telecom.get("value", "")
            if sys == "phone":
                telecom_xml += f'      <telecom value="tel:{val}"/>\n'
            elif sys == "email":
                telecom_xml += f'      <telecom value="mailto:{val}"/>\n'

        addr_xml = ""
        for addr in patient.get("address", []):
            line = ""
            if addr.get("line"):
                lines = addr["line"]
                if isinstance(lines, list) and lines:
                    line = lines[0]
                elif isinstance(lines, str):
                    line = lines
            city = addr.get("city", "")
            state = addr.get("state", "")
            postal = addr.get("postalCode", "")
            parts = [
                f'        <streetAddressLine>{line}</streetAddressLine>' if line else "",
                f'        <city>{city}</city>' if city else "",
                f'        <state>{state}</state>' if state else "",
                f'        <postalCode>{postal}</postalCode>' if postal else "",
            ]
            addr_xml = "      <addr>\n" + "\n".join(filter(None, parts)) + "\n      </addr>"

        return f'''  <recordTarget>
    <patientRole>
      <id root="2.16.840.1.113883.19.5" extension="{mrn or 'unknown'}"/>
      <patient>
        <name>
          <given>{_escape_xml(given)}</given>
          <family>{_escape_xml(family)}</family>
        </name>
        <administrativeGenderCode code="{gender_map.get(gender, 'UN')}" codeSystem="2.16.840.1.113883.5.1"/>
        <birthTime value="{birth_date.replace('-', '')}"/>
      </patient>
{addr_xml}
{telecom_xml}    </patientRole>
  </recordTarget>'''

    @staticmethod
    def _ccda_author_xml() -> str:
        """Generate C-CDA author element."""
        now_iso = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f'''  <author>
    <time value="{now_iso}"/>
    <assignedAuthor>
      <id root="2.16.840.1.113883.19.5" extension="healthbridge"/>
      <representedOrganization>
        <id root="2.16.840.1.113883.19.5" extension="healthbridge-org"/>
        <name>HealthBridge Platform</name>
      </representedOrganization>
    </assignedAuthor>
  </author>'''

    @staticmethod
    def _ccda_custodian_xml() -> str:
        return '''  <custodian>
    <assignedCustodian>
      <representedCustodianOrganization>
        <id root="2.16.840.1.113883.19.5" extension="healthbridge-org"/>
        <name>HealthBridge Platform</name>
      </representedCustodianOrganization>
    </assignedCustodian>
  </custodian>'''

    @staticmethod
    def _ccda_section_wrapper(
        title: str,
        loinc_code: str,
        loinc_name: str,
        resources: list[dict],
        entry_fn: callable,
    ) -> str:
        """Wrap a list of FHIR resources into a C-CDA section."""
        entries_xml = "\n".join(entry_fn(r) for r in resources)
        return f'''      <component>
        <section>
          <templateId root="2.16.840.1.113883.10.20.22.2.1"/>
          <code code="{loinc_code}" codeSystem="2.16.840.1.113883.6.1" displayName="{_escape_xml(loinc_name)}"/>
          <title>{_escape_xml(title)}</title>
          <text>{_escape_xml(title)} - {len(resources)} entr{('ies' if len(resources) != 1 else 'y')}</text>
{entries_xml}        </section>
      </component>'''

    @staticmethod
    def _ccda_condition_entry_xml(cond: dict) -> str:
        code = cond.get("code", {})
        coding = (code.get("coding") or [{}])[0]
        entry_id = str(uuid.uuid4())
        status = cond.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "active")
        onset = cond.get("onsetDateTime", cond.get("recordedDate", ""))[:10] or "20200101"

        return f'''          <entry>
            <act classCode="ACT" moodCode="EVN">
              <templateId root="2.16.840.1.113883.10.20.22.4.3"/>
              <id root="{entry_id}"/>
              <code code="{escape_attr(coding.get('code', ''))}" codeSystem="{escape_attr(coding.get('system', SNOMED))}" displayName="{escape_attr(coding.get('display', ''))}"/>
              <statusCode code="{status}"/>
              <effectiveTime><low value="{onset}"/></effectiveTime>
            </act>
          </entry>'''

    @staticmethod
    def _ccda_medication_entry_xml(mr: dict) -> str:
        med_cc = mr.get("medicationCodeableConcept", {}) or mr.get("medicationReference", {})
        coding = (med_cc.get("coding") or [{}])[0]
        entry_id = str(uuid.uuid4())
        dose_inst = mr.get("dosageInstruction", [])
        dose_str = ""
        if dose_inst:
            d = dose_inst[0]
            dar = d.get("doseAndRate", [])
            if dar and dar[0].get("doseQuantity"):
                dq = dar[0]["doseQuantity"]
                dose_str = f'      <doseQuantity value="{dq.get("value", "")}" unit="{escape_attr(dq.get("unit", ""))}"/>\n'

        return f'''          <entry>
            <substanceAdministration classCode="SBADM" moodCode="RQO">
              <templateId root="2.16.840.1.113883.10.20.22.4.16"/>
              <id root="{entry_id}"/>
              <consumable>
                <manufacturedProduct>
                  <manufacturedMaterial>
                    <code code="{escape_attr(coding.get('code', ''))}" codeSystem="{escape_attr(coding.get('system', RXNORM))}" displayName="{escape_attr(coding.get('display', ''))}"/>
                  </manufacturedMaterial>
                </manufacturedProduct>
              </consumable>
{dose_str}      <statusCode code="active"/>
            </substanceAdministration>
          </entry>'''

    @staticmethod
    def _ccda_observation_entry_xml(obs: dict) -> str:
        code = obs.get("code", {})
        coding = (code.get("coding") or [{}])[0]
        entry_id = str(uuid.uuid4())
        value = obs.get("valueQuantity", {}) or obs.get("valueString", "")
        val_xml = ""
        if isinstance(value, dict):
            val_xml = f'value="{value.get("value", "")}" unit="{escape_attr(value.get("unit", ""))}"'
        else:
            val_xml = f'value="{escape_attr(str(value))}"'

        return f'''          <entry>
            <observation classCode="OBS" moodCode="EVN">
              <templateId root="2.16.840.1.113883.10.20.22.4.2"/>
              <id root="{entry_id}"/>
              <code code="{escape_attr(coding.get('code', ''))}" codeSystem="{escape_attr(coding.get('system', LOINC))}" displayName="{escape_attr(coding.get('display', ''))}"/>
              <value xsi:type="PQ" {val_xml}/>
            </observation>
          </entry>'''

    @staticmethod
    def _ccda_procedure_entry_xml(proc: dict) -> str:
        code = proc.get("code", {})
        coding = (code.get("coding") or [{}])[0]
        entry_id = str(uuid.uuid4())
        perf_date = (proc.get("performedDateTime", "") or
                     proc.get("performedPeriod", {}).get("start", ""))[:10]

        return f'''          <entry>
            <procedure classCode="PROC" moodCode="EVN">
              <templateId root="2.16.840.1.113883.10.20.22.4.14"/>
              <id root="{entry_id}"/>
              <code code="{escape_attr(coding.get('code', ''))}" codeSystem="{escape_attr(coding.get('system', SNOMED))}" displayName="{escape_attr(coding.get('display', ''))}"/>
              <effectiveTime><low value="{perf_date or '20200101'}"/></effectiveTime>
            </procedure>
          </entry>'''

    @staticmethod
    def _ccda_encounter_entry_xml(enc: dict) -> str:
        enc_type = enc.get("type", [{}])[0] if enc.get("type") else {}
        coding = (enc_type.get("coding") or [{}])[0]
        entry_id = str(uuid.uuid4())
        period = enc.get("period", {})
        start = (period.get("start", "")[:10] or "20200101").replace("-", "")

        return f'''          <entry>
            <encounter classCode="ENC" moodCode="EVN">
              <templateId root="2.16.840.1.113883.10.20.22.4.49"/>
              <id root="{entry_id}"/>
              <code code="{escape_attr(coding.get('code', ''))}" codeSystem="{escape_attr(coding.get('system', '2.16.840.1.113883.6.96'))}" displayName="{escape_attr(coding.get('display', ''))}"/>
              <effectiveTime><low value="{start}"/></effectiveTime>
            </encounter>
          </entry>'''

    @staticmethod
    def _ccda_allergy_entry_xml(allerg: dict) -> str:
        code = allerg.get("code", {})
        coding = (code.get("coding") or [{}])[0]
        entry_id = str(uuid.uuid4())

        return f'''          <entry>
            <act classCode="ACT" moodCode="EVN">
              <templateId root="2.16.840.1.113883.10.20.22.4.30"/>
              <id root="{entry_id}"/>
              <code code="{escape_attr(coding.get('code', ''))}" codeSystem="{escape_attr(coding.get('system', SNOMED))}" displayName="{escape_attr(coding.get('display', ''))}"/>
              <statusCode code="active"/>
            </act>
          </entry>'''

    @staticmethod
    def _ccda_immunization_entry_xml(imm: dict) -> str:
        vaccine = imm.get("vaccineCode", {})
        coding = (vaccine.get("coding") or [{}])[0]
        entry_id = str(uuid.uuid4())
        occ_date = (imm.get("occurrenceDateTime", "")[:10] or "20200101").replace("-", "")

        return f'''          <entry>
            <substanceAdministration classCode="SBADM" moodCode="EVN">
              <templateId root="2.16.840.1.113883.10.20.22.4.52"/>
              <id root="{entry_id}"/>
              <consumable>
                <manufacturedProduct>
                  <manufacturedMaterial>
                    <code code="{escape_attr(coding.get('code', ''))}" codeSystem="{escape_attr(coding.get('system', '2.16.840.1.113883.12.292'))}" displayName="{escape_attr(coding.get('display', ''))}"/>
                  </manufacturedMaterial>
                </manufacturedProduct>
              </consumable>
              <effectiveTime><center value="{occ_date}"/></effectiveTime>
            </substanceAdministration>
          </entry>'''

    # ══════════════════════════════════════════════════════════════════════
    # Private: HL7 v2 Parsing Helpers
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _hl7_parse_segments(hl7_str: str) -> dict[str, list[dict]]:
        """Parse an HL7 v2 pipe-delimited message into segments dict."""
        segments: dict[str, list[dict]] = {}
        lines = hl7_str.strip().split("\n")

        for line in lines:
            line = line.strip().replace("\r", "")
            if not line:
                continue
            parts = line.split("|")
            if not parts:
                continue

            seg_id = parts[0].strip()
            if not seg_id:
                continue

            seg_dict: dict[str, Any] = {
                "raw": line,
                "fields": {},
            }

            for i, field in enumerate(parts[1:], start=1):
                seg_dict["fields"][str(i)] = field

            segments.setdefault(seg_id, []).append(seg_dict)

        return segments

    @staticmethod
    def _hl7_field(seg: dict, field_num: str, default: str = "") -> str:
        """Get a field value from an HL7 segment dict."""
        return seg.get("fields", {}).get(field_num, default)

    @staticmethod
    def _hl7_subfield(field: str, sub: int = 0, default: str = "") -> str:
        """Get a subfield (^ separated) from an HL7 field value."""
        if not field:
            return default
        parts = field.split("^")
        return parts[sub] if sub < len(parts) else default

    def _hl7_adt_patient(self, segments: dict) -> Patient | None:
        """Extract Patient from ADT message PID segment."""
        pid_list = segments.get("PID", [])
        if not pid_list:
            return None
        pid = pid_list[0]

        patient = Patient.model_construct()
        patient.id = str(uuid.uuid4())
        patient.active = True

        # Identifiers
        ids = []
        cx1 = self._hl7_field(pid, "2")  # Patient ID
        if cx1:
            identifier = Identifier.model_construct()
            identifier.value = self._hl7_subfield(cx1, 0)
            identifier.system = "urn:oid:2.16.840.1.113883.19.5"
            ids.append(identifier)

        cx3 = self._hl7_field(pid, "3")  # Patient Identifier List
        if cx3:
            for _cx in cx3.split("\r"):
                id_val = self._hl7_subfield(cx3, 0)
                if id_val:
                    identifier = Identifier.model_construct()
                    identifier.value = id_val
                    id_type = self._hl7_subfield(cx3, 4)
                    if id_type:
                        identifier.type = CodeableConcept.model_construct(
                            coding=[Coding.model_construct(
                                code=id_type,
                                display=id_type,
                            )]
                        )
                    ids.append(identifier)

        if ids:
            patient.identifier = ids

        # Name
        xpn5 = self._hl7_field(pid, "5")  # Patient Name
        if xpn5:
            hn = HumanName.model_construct()
            parts = xpn5.split("^")
            hn.family = parts[0] if len(parts) > 0 else ""
            hn.given = [parts[1]] if len(parts) > 1 else None
            hn.use = "official"
            patient.name = [hn]

        # DOB
        ts7 = self._hl7_field(pid, "7")
        if ts7:
            dob = ts7[:8]
            if len(dob) == 8:
                patient.birthDate = f"{dob[:4]}-{dob[4:6]}-{dob[6:8]}"

        # Gender
        sex8 = self._hl7_field(pid, "8")
        g_map = {"M": "male", "F": "female", "O": "other", "U": "unknown"}
        patient.gender = g_map.get(sex8, "unknown")

        # Address
        xad11 = self._hl7_field(pid, "11")
        if xad11:
            parts = xad11.split("^")
            from fhir.resources.address import Address
            addr = Address.model_construct()
            line = parts[0] if len(parts) > 0 else ""
            if line:
                addr.line = [line]
            if len(parts) > 2:
                addr.city = parts[2]
            if len(parts) > 3:
                addr.state = parts[3]
            if len(parts) > 4:
                addr.postalCode = parts[4]
            patient.address = [addr]

        # Phone
        xpn13 = self._hl7_field(pid, "13")
        if xpn13:
            phone = self._hl7_subfield(xpn13, 0)
            if phone:
                ct = ContactPoint.model_construct()
                ct.system = "phone"
                ct.value = phone
                patient.telecom = [ct]

        return patient

    def _hl7_adt_encounter(self, segments: dict) -> Encounter | None:
        """Extract Encounter from ADT message PV1 segment."""
        pv1_list = segments.get("PV1", [])
        if not pv1_list:
            return None
        pv1 = pv1_list[0]

        # Class
        pv1_2 = self._hl7_field(pv1, "2")  # Patient Class
        cls_map = {
            "I": "IMP", "O": "AMB", "E": "EMER",
            "P": "PRENC", "R": "REHAB",
        }
        cl = cls_map.get(pv1_2, "AMB")

        # Period
        pv1_44 = self._hl7_field(pv1, "44")
        pv1_45 = self._hl7_field(pv1, "45")
        period_dict = None
        if pv1_44:
            dt = self._hl7_to_datetime(pv1_44)
            if pv1_45:
                dt_end = self._hl7_to_datetime(pv1_45)
                period_dict = {"start": dt, "end": dt_end}
            else:
                period_dict = {"start": dt}

        # Type
        type_list = None
        pv1_4 = self._hl7_field(pv1, "4")
        if pv1_4:
            type_list = [{
                "coding": [{
                    "code": self._hl7_subfield(pv1_4, 0),
                    "display": self._hl7_subfield(pv1_4, 1),
                }]
            }]

        enc = Encounter.model_construct(
            id=str(uuid.uuid4()),
            status="finished",
            subject=Reference.model_construct(reference="urn:uuid:placeholder"),
            class_fhir=Coding.model_construct(
                system="http://terminology.hl7.org/CodeSystem/v3-ActCode",
                code=cl,
            ),
            type=type_list,
            period=Period.model_construct(**period_dict) if period_dict else None,
        )
        return enc

    def _hl7_oru_observations(self, segments: dict) -> list[Observation]:
        """Extract Observation resources from ORU message OBX segments."""
        obx_list = segments.get("OBX", [])
        observations: list[Observation] = []

        for obx in obx_list:
            # OBX-3: Observation Identifier
            obx_3 = self._hl7_field(obx, "3")
            code_dict = None
            if obx_3:
                code_dict = {
                    "coding": [{
                        "code": self._hl7_subfield(obx_3, 0),
                        "display": self._hl7_subfield(obx_3, 1),
                        "system": self._hl7_subfield(obx_3, 2) or LOINC,
                    }]
                }

            # OBX-5: Observation Value
            obx_5 = self._hl7_field(obx, "5")
            obx_2 = self._hl7_field(obx, "2")  # Value Type
            obx_6 = self._hl7_field(obx, "6")  # Units
            value_quantity = None
            value_string = None
            value_codeable_concept = None
            if obx_5:
                if obx_2 in ("NM", "SN"):
                    unit_parts = obx_6.split("^") if obx_6 else []
                    try:
                        value_quantity = {"value": float(obx_5), "unit": unit_parts[0] if unit_parts else None, "system": UCUM, "code": unit_parts[0] if unit_parts else None}
                    except (ValueError, TypeError):
                        value_string = obx_5
                elif obx_2 == "ST":
                    value_string = obx_5
                elif obx_2 in ("CE", "CWE"):
                    parts = obx_5.split("^")
                    value_codeable_concept = {
                        "coding": [{
                            "code": parts[0] if len(parts) > 0 else "",
                            "display": parts[1] if len(parts) > 1 else "",
                            "system": parts[2] if len(parts) > 2 else "",
                        }]
                    }

            # OBX-14: Date/Time of Observation
            obx_14 = self._hl7_field(obx, "14")
            effective_dt = self._hl7_to_datetime(obx_14) if obx_14 else datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            # OBX-7: Reference Range
            obx_7 = self._hl7_field(obx, "7")
            reference_range = None
            if obx_7:
                ranges = obx_7.split("-")
                if len(ranges) == 2:
                    try:
                        reference_range = [{"low": {"value": float(ranges[0])}, "high": {"value": float(ranges[1])}}]
                    except (ValueError, TypeError):
                        pass

            # OBX-8: Abnormal Flags
            obx_8 = self._hl7_field(obx, "8")
            interpretation = None
            if obx_8:
                interpretation = [{"coding": [{"code": obx_8, "display": obx_8}]}]

            obs = Observation.model_construct(
                id=str(uuid.uuid4()),
                status="final",
                subject=Reference.model_construct(reference="urn:uuid:placeholder"),
                code=code_dict,
                valueQuantity=value_quantity,
                valueString=value_string,
                valueCodeableConcept=value_codeable_concept,
                effectiveDateTime=effective_dt,
                referenceRange=reference_range,
                interpretation=interpretation,
            )
            observations.append(obs)

        return observations

    def _hl7_oru_diagnostic_report(self, segments: dict,
                                    observations: list[Observation]) -> DiagnosticReport | None:
        """Extract DiagnosticReport from ORU message."""
        obr_list = segments.get("OBR", [])
        if not obr_list:
            return None

        obr = obr_list[0]

        dr = DiagnosticReport.model_construct()
        dr.id = str(uuid.uuid4())
        dr.status = "final"
        dr.subject = Reference.model_construct(reference="urn:uuid:placeholder")

        # OBR-4: Universal Service ID
        obr_4 = self._hl7_field(obr, "4")
        if obr_4:
            dr.code = CodeableConcept.model_construct()
            dr.code.coding = [
                Coding.model_construct(
                    code=self._hl7_subfield(obr_4, 0),
                    display=self._hl7_subfield(obr_4, 1),
                    system=self._hl7_subfield(obr_4, 2) or LOINC,
                )
            ]

        # OBR-7: Observation Date/Time
        obr_7 = self._hl7_field(obr, "7")
        if obr_7:
            dr.effectiveDateTime = self._hl7_to_datetime(obr_7)

        # Link observations
        obs_refs = []
        for obs in observations:
            obs_refs.append(Reference.model_construct(reference=f"urn:uuid:{obs.id}"))
        if obs_refs:
            dr.result = obs_refs

        return dr

    def _hl7_rde_medication_request(self, segments: dict) -> MedicationRequest | None:
        """Extract MedicationRequest from RDE message."""
        # RXE segment has pharmacy order data
        rxe_list = segments.get("RXE", [])
        if not rxe_list:
            return None
        rxe = rxe_list[0]

        mr = MedicationRequest.model_construct()
        mr.id = str(uuid.uuid4())
        mr.status = "active"
        mr.intent = "order"
        mr.subject = Reference.model_construct(reference="urn:uuid:placeholder")

        # RXE-2: Give Code
        rxe_2 = self._hl7_field(rxe, "2")
        if rxe_2:
            mr.medicationCodeableConcept = CodeableConcept.model_construct()
            mr.medicationCodeableConcept.coding = [
                Coding.model_construct(
                    code=self._hl7_subfield(rxe_2, 0),
                    display=self._hl7_subfield(rxe_2, 1),
                    system=RXNORM,
                )
            ]

        # RXE-3: Dosage
        rxe_3 = self._hl7_field(rxe, "3")
        if rxe_3:
            dose_parts = rxe_3.split("^")
            try:
                dosage = Dosage.model_construct()
                from fhir.resources.dosage import DosageDoseAndRate
                dar = DosageDoseAndRate.model_construct()
                dar.doseQuantity = Quantity.model_construct(
                    value=float(dose_parts[0]) if dose_parts else None,
                    unit=dose_parts[1] if len(dose_parts) > 1 else None,
                )
                dosage.doseAndRate = [dar]
                mr.dosageInstruction = [dosage]
            except (ValueError, IndexError):
                pass

        # RXE-7: Route
        rxe_7 = self._hl7_field(rxe, "7")
        if rxe_7:
            if not mr.dosageInstruction:
                mr.dosageInstruction = [Dosage.model_construct()]
            mr.dosageInstruction[0].route = CodeableConcept.model_construct(
                coding=[Coding.model_construct(
                    code=self._hl7_subfield(rxe_7, 0),
                    display=self._hl7_subfield(rxe_7, 1),
                )]
            )

        return mr

    def _hl7_siu_encounter(self, segments: dict) -> Encounter | None:
        """Extract Encounter from SIU message (AIS + SCH segments)."""
        sch_list = segments.get("SCH", [])
        if not sch_list:
            return None
        sch = sch_list[0]

        # SCH-11: Appointment Reason
        type_list = None
        sch_11 = self._hl7_field(sch, "11")
        if sch_11:
            type_list = [{
                "coding": [{
                    "code": self._hl7_subfield(sch_11, 0),
                    "display": self._hl7_subfield(sch_11, 1),
                }]
            }]

        # SCH-8: Start Date/Time
        period_dict = None
        sch_8 = self._hl7_field(sch, "8")
        if sch_8:
            start_dt = self._hl7_to_datetime(sch_8)
            period_dict = {"start": start_dt}

        enc = Encounter.model_construct(
            id=str(uuid.uuid4()),
            status="planned",
            subject=Reference.model_construct(reference="urn:uuid:placeholder"),
            type=type_list,
            class_fhir=Coding.model_construct(
                system="http://terminology.hl7.org/CodeSystem/v3-ActCode",
                code="AMB",
            ),
            period=Period.model_construct(**period_dict) if period_dict else None,
        )
        return enc

    def _hl7_vxu_immunization(self, segments: dict) -> Immunization | None:
        """Extract Immunization from VXU message."""
        rxa_list = segments.get("RXA", [])
        if not rxa_list:
            return None
        rxa = rxa_list[0]

        imm = Immunization.model_construct()
        imm.id = str(uuid.uuid4())
        imm.status = "completed"
        imm.patient = Reference.model_construct(reference="urn:uuid:placeholder")

        # RXA-5: Administered Code
        rxa_5 = self._hl7_field(rxa, "5")
        if rxa_5:
            imm.vaccineCode = CodeableConcept.model_construct()
            imm.vaccineCode.coding = [
                Coding.model_construct(
                    code=self._hl7_subfield(rxa_5, 0),
                    display=self._hl7_subfield(rxa_5, 1),
                    system=SNOMED,
                )
            ]

        # RXA-3: Date/Time Administered
        rxa_3 = self._hl7_field(rxa, "3")
        if rxa_3:
            imm.occurrenceDateTime = self._hl7_to_datetime(rxa_3)

        return imm

    def _hl7_mdm_document(self, segments: dict) -> DocumentReference | None:
        """Extract DocumentReference from MDM message."""
        tx_list = segments.get("TX", []) or segments.get("OBX", [])
        if not tx_list:
            return None

        doc_ref = DocumentReference.model_construct()
        doc_ref.id = str(uuid.uuid4())
        doc_ref.status = "current"
        doc_ref.subject = Reference.model_construct(reference="urn:uuid:placeholder")

        doc_ref.type = CodeableConcept.model_construct(
            coding=[Coding.model_construct(
                system=LOINC,
                code="34133-9",
                display="Summarization of Episode Note",
            )]
        )

        # Build attachment from TX segments
        doc_content = "\n".join(
            self._hl7_field(tx, "5") or self._hl7_field(tx, "6") or ""
            for tx in tx_list
        )

        doc_ref.content = [
            DocumentReference.model_construct(
                **{"attachment": Attachment.model_construct(
                    contentType="text/plain",
                    data=doc_content.encode("utf-8").hex() if doc_content else "",
                    title="MDM Document",
                )}
            )
        ]

        # TXA segment for dates
        txa_list = segments.get("TXA", [])
        if txa_list:
            txa = txa_list[0]
            txa_16 = self._hl7_field(txa, "16")
            if txa_16:
                doc_ref.date = self._hl7_to_datetime(txa_16)

        return doc_ref

    @staticmethod
    def _hl7_to_datetime(ts: str) -> str:
        """Convert HL7 v2 timestamp to FHIR ISO datetime."""
        clean = ts.replace("^", "").strip()
        if not clean:
            return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        # HL7 format: YYYYMMDDHHMMSS
        if len(clean) >= 14:
            return (f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}T"
                    f"{clean[8:10]}:{clean[10:12]}:{clean[12:14]}Z")
        elif len(clean) >= 8:
            return f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}"
        elif len(clean) >= 4:
            return clean[:4]
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # ══════════════════════════════════════════════════════════════════════
    # Private: FHIR Validation Helpers
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _validate_resource_required_fields(
        resource: dict,
        resource_type: str,
        result: dict,
    ) -> None:
        """Check required fields for each FHIR resource type."""
        if not resource:
            return

        rid = resource.get("id", "?")

        # Common: all resources need resourceType
        if not resource.get("resourceType"):
            result["errors"].append(f"{rid}: Missing resourceType")

        # Patient
        if resource_type == "Patient":
            if not resource.get("name"):
                result["errors"].append(f"{rid}: Patient missing required 'name' field")
            if not resource.get("gender"):
                result["warnings"].append(f"{rid}: Patient missing 'gender'")

        # Condition
        elif resource_type == "Condition":
            if not resource.get("subject"):
                result["errors"].append(f"{rid}: Condition missing required 'subject'")
            if not resource.get("code"):
                result["errors"].append(f"{rid}: Condition missing required 'code'")
            if not resource.get("clinicalStatus"):
                result["errors"].append(f"{rid}: Condition missing required 'clinicalStatus'")

        # Observation
        elif resource_type == "Observation":
            if not resource.get("status"):
                result["errors"].append(f"{rid}: Observation missing required 'status'")
            if not resource.get("code"):
                result["errors"].append(f"{rid}: Observation missing required 'code'")
            if not resource.get("subject"):
                result["errors"].append(f"{rid}: Observation missing required 'subject'")

        # MedicationRequest
        elif resource_type == "MedicationRequest":
            if not resource.get("status"):
                result["errors"].append(f"{rid}: MedicationRequest missing 'status'")
            if not resource.get("intent"):
                result["errors"].append(f"{rid}: MedicationRequest missing 'intent'")
            if not resource.get("subject"):
                result["errors"].append(f"{rid}: MedicationRequest missing 'subject'")
            if not resource.get("medicationCodeableConcept") and not resource.get("medicationReference"):
                result["errors"].append(f"{rid}: MedicationRequest missing medication")

        # DiagnosticReport
        elif resource_type == "DiagnosticReport":
            if not resource.get("status"):
                result["errors"].append(f"{rid}: DiagnosticReport missing 'status'")
            if not resource.get("code"):
                result["errors"].append(f"{rid}: DiagnosticReport missing 'code'")
            if not resource.get("subject"):
                result["errors"].append(f"{rid}: DiagnosticReport missing 'subject'")

        # Procedure
        elif resource_type == "Procedure":
            if not resource.get("status"):
                result["errors"].append(f"{rid}: Procedure missing 'status'")
            if not resource.get("subject"):
                result["errors"].append(f"{rid}: Procedure missing 'subject'")
            if not resource.get("code"):
                result["errors"].append(f"{rid}: Procedure missing 'code'")

        # Encounter
        elif resource_type == "Encounter":
            if not resource.get("status"):
                result["errors"].append(f"{rid}: Encounter missing 'status'")
            if not resource.get("subject"):
                result["errors"].append(f"{rid}: Encounter missing 'subject'")
            if not resource.get("class"):
                result["errors"].append(f"{rid}: Encounter missing 'class'")

        # AllergyIntolerance
        elif resource_type == "AllergyIntolerance":
            if not resource.get("patient"):
                result["errors"].append(f"{rid}: AllergyIntolerance missing 'patient'")
            if not resource.get("code"):
                result["errors"].append(f"{rid}: AllergyIntolerance missing 'code'")

        # Immunization
        elif resource_type == "Immunization":
            if not resource.get("status"):
                result["errors"].append(f"{rid}: Immunization missing 'status'")
            if not resource.get("vaccineCode"):
                result["errors"].append(f"{rid}: Immunization missing 'vaccineCode'")
            if not resource.get("patient"):
                result["errors"].append(f"{rid}: Immunization missing 'patient'")

        # DocumentReference
        elif resource_type == "DocumentReference":
            if not resource.get("status"):
                result["errors"].append(f"{rid}: DocumentReference missing 'status'")
            if not resource.get("content"):
                result["errors"].append(f"{rid}: DocumentReference missing 'content'")

    @staticmethod
    def _validate_fhir_bundle(bundle_dict: dict) -> tuple[int, int]:
        """Run basic structural validation on a FHIR Bundle dict.

        Returns (error_count, warning_count).
        """
        errors = 0
        warnings = 0

        if not bundle_dict:
            return 1, 0

        bt = bundle_dict.get("type")
        if not bt:
            errors += 1
        if bt and bt not in ("document", "collection", "batch", "transaction",
                             "history", "searchset", "message"):
            warnings += 1

        entries = bundle_dict.get("entry", [])
        for entry in entries:
            resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
            rt = resource.get("resourceType", "Unknown")
            rid = resource.get("id", "?")
            if not rt:
                errors += 1
                continue
            if not rid:
                warnings += 1

            if rt == "Patient" and not resource.get("name"):
                errors += 1

        return errors, warnings

    # ══════════════════════════════════════════════════════════════════════
    # Private: PDF Formatting Helpers
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _pdf_label_value(label: str, value: str, styles: Any) -> Table:
        """Create a label-value row table for PDF layout."""
        label_style = ParagraphStyle(
            "label", parent=styles["Normal"], fontSize=8,
            textColor=colors.HexColor("#555555"),
        )
        value_style = ParagraphStyle(
            "val", parent=styles["Normal"], fontSize=10,
            spaceAfter=2,
        )
        t = Table(
            [[Paragraph(label, label_style), Paragraph(value, value_style)]],
            colWidths=[50 * mm, 105 * mm],
        )
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return t

    # ══════════════════════════════════════════════════════════════════════
    # Private: FHIR Utility Helpers
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _coding_display(codeable: dict) -> str:
        """Extract first display text from a CodeableConcept dict."""
        if not codeable:
            return ""
        codings = codeable.get("coding", [])
        for c in codings:
            if c.get("display"):
                return c["display"]
        return codeable.get("text", "")

    @staticmethod
    def _fhir_human_name(name: dict) -> str:
        """Format a HumanName dict to 'Given Family' string."""
        given = name.get("given", [])
        given_str = given[0] if isinstance(given, list) and given else given if isinstance(given, str) else ""
        family = name.get("family", "")
        prefix = name.get("prefix", [None])[0] if name.get("prefix") else ""
        parts = [p for p in [prefix, given_str, family] if p]
        return " ".join(parts)

    @staticmethod
    def _fhir_identifier_value(identifiers: list, type_code: str) -> str:
        """Find an identifier value by type coding."""
        for ident in identifiers:
            coding = ident.get("type", {}).get("coding", [])
            for c in coding:
                if c.get("code") == type_code:
                    return ident.get("value", "")
        # Fallback: return first identifier value
        return identifiers[0].get("value", "") if identifiers else "N/A"

    @staticmethod
    def _fhir_observation_value(obs: dict) -> str:
        """Extract the human-readable value from an Observation dict."""
        # Try valueQuantity
        vq = obs.get("valueQuantity")
        if vq:
            val = vq.get("value", "")
            unit = vq.get("unit", "")
            return f"{val} {unit}".strip()

        # Try valueCodeableConcept
        vcc = obs.get("valueCodeableConcept")
        if vcc:
            return FhirConversionService._coding_display(vcc)

        # Try valueString
        vs = obs.get("valueString")
        if vs:
            return vs

        # Try valueBoolean
        vb = obs.get("valueBoolean")
        if vb is not None:
            return str(vb)

        # Try valueInteger
        vi = obs.get("valueInteger")
        if vi is not None:
            return str(vi)

        # Try valueRange
        vr = obs.get("valueRange")
        if vr:
            low = vr.get("low", {}).get("value", "")
            high = vr.get("high", {}).get("value", "")
            unit = (vr.get("low", {}) or vr.get("high", {})).get("unit", "")
            return f"{low} - {high} {unit}".strip()

        return "N/A"

    # ══════════════════════════════════════════════════════════════════════
    # Private: Audit Logging
    # ══════════════════════════════════════════════════════════════════════

    def _log_conversion(
        self,
        source_format: str,
        target_format: str,
        success: bool,
        start_time: float,
        result: dict,
    ) -> None:
        """Log a conversion event to the database (if session available)."""
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        log_entry = {
            "source_format": source_format,
            "target_format": target_format,
            "success": success,
            "processing_time_ms": elapsed_ms,
            "resources_converted": result.get("resources_converted", 0),
            "validation_errors": result.get("validation_errors", 0),
            "validation_warnings": result.get("validation_warnings", 0),
            "error_message": result.get("error_message"),
        }

        logger.info(
            "Conversion | %s → %s | %s | %dms | %d resources | %d errors | %d warnings",
            source_format, target_format,
            "SUCCESS" if success else "FAILURE",
            elapsed_ms,
            log_entry["resources_converted"],
            log_entry["validation_errors"],
            log_entry["validation_warnings"],
        )

        # Store in the result dict for caller access
        result["_conversion_log"] = log_entry

        # Persist to DB if session is available
        if self.db_session is not None:
            try:
                from app.models import ConversionLog
                db_entry = ConversionLog(**{
                    k: v for k, v in log_entry.items()
                    if k in ("source_format", "target_format", "success",
                             "processing_time_ms", "resources_converted",
                             "validation_errors", "validation_warnings",
                             "error_message")
                })
                db_entry.fhir_version = FHIR_VERSION
                self.db_session.add(db_entry)
                if hasattr(self.db_session, "commit"):
                    self.db_session.commit()
            except Exception as exc:
                logger.warning("Failed to persist conversion log: %s", exc)


# ═════════════════════════════════════════════════════════════════════════════
# Module-level helpers
# ═════════════════════════════════════════════════════════════════════════════

_CCDA_OID_MAP = {
    "2.16.840.1.113883.6.96": SNOMED,
    "2.16.840.1.113883.6.1": LOINC,
    "2.16.840.1.113883.6.3": ICD_10,
    "2.16.840.1.113883.6.88": RXNORM,
    "2.16.840.1.113883.6.8": "http://www.ama-assn.org/go/cpt",
    "2.16.840.1.113883.5.1": "http://terminology.hl7.org/CodeSystem/v3-AdministrativeGender",
    "2.16.840.1.113883.5.4": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
    "2.16.840.1.113883.5.25": "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",
    "2.16.840.1.113883.6.12": "http://hl7.org/fhir/sid/icd-10-cm",
    "2.16.840.1.113883.6.59": "http://hl7.org/fhir/sid/icd-10-pcs",
    "2.16.840.1.113883.6.238": "http://hl7.org/fhir/sid/cvx",
    "2.16.840.1.113883.12.292": "http://hl7.org/fhir/sid/cvx",
}


def _ccda_oid_to_system(oid: str) -> str:
    """Map C-CDA OID to FHIR system URL."""
    return _CCDA_OID_MAP.get(oid, f"urn:oid:{oid}" if oid else "")


def _escape_xml(text: str) -> str:
    """Escape text for XML output."""
    if not text:
        return ""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def escape_attr(text: str) -> str:
    """Escape text for XML attribute value."""
    return _escape_xml(text)


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

conversion_service = FhirConversionService()
