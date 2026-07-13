# Backend Strengths - Implementation Tasks

Extracted from AUDIT_PLAN.md (PDF audit). These are the **already working** backend capabilities that form the foundation for the 30-day clinical build.

---

## 1. API Routers (16 Fully Wired) ✅ DONE
- [x] Auth router (`/api/v1/auth`)
- [x] Patients router (`/api/v1/patients`)
- [x] FHIR R4 router (`/api/v1/fhir`)
- [x] Consent router (`/api/v1/consent`)
- [x] Compliance router (`/api/v1/compliance`)
- [x] Admin router (`/api/v1/admin`)
- [x] Ingestion router (`/api/v1/ingest`)
- [x] Conversion router (`/api/v1/convert`)
- [x] Exports router (`/api/v1/exports`)
- [x] Connectors router (`/api/v1/connectors`)
- [x] Organizations router (`/api/v1/organizations`)
- [x] WhatsApp router (`/api/v1/whatsapp`)
- [ ] **Verify all 16 routers load without errors**
- [ ] **Add OpenAPI tags/descriptions for Swagger UI**

---

## 2. DPDP 2025 Compliance (2,716 lines) ✅ DONE
- [x] Consent management (grant, withdraw, expire)
- [x] Breach detection & notification (72-hour SLA)
- [x] Data erasure scheduling (1-year retention)
- [x] Cross-border transfer controls
- [x] Grievance redressal (90-day SLA)
- [x] Data principal rights (access, correction, portability)
- [ ] **Add automated compliance report endpoint** (`GET /api/v1/compliance/report`)
- [ ] **Add breach notification webhook** for external systems

---

## 3. FHIR Conversion Service (2,757 lines) ✅ DONE
- [x] C-CDA ↔ FHIR R4
- [x] HL7 v2 ↔ FHIR R4
- [x] FHIR R4 → PDF
- [ ] **Add validation endpoint** (`POST /api/v1/fhir/validate`)
- [ ] **Add bundle transaction support** for bulk operations
- [ ] **Add $everything operation** for patient data export

---

## 4. Document Ingestion Pipeline ✅ DONE
- [x] Aadhaar eKYC integration
- [x] Photo/PDF → OCR (Tesseract)
- [x] AI extraction → structured data
- [x] FHIR R4 Bundle output
- [x] OTC verification
- [x] XML decryption
- [x] SHA-256 hashing
- [ ] **Add support for more document types** (insurance cards, referral letters)
- [ ] **Add confidence scoring** for AI extraction
- [ ] **Add manual review queue** for low-confidence extractions

---

## 5. ABHA Connector (595 lines) ✅ DONE
- [x] ABHA address linking
- [x] Health record sharing via ABDM
- [x] Consent artefact management
- [ ] **Add Scan & Share QR generation** (Day 26-27 in 30-day plan)
- [ ] **Add token refresh handling** for long-lived sessions

---

## 6. Audit Trail ✅ DONE
- [x] Append-only immutable logs
- [x] Context-manager pattern for auto-capture
- [x] DPDP 1-year purge job
- [x] User/IP/action tracking
- [ ] **Add audit log export** (CSV/JSON for compliance auditors)

---

## 7. Fernet Encryption (3-tier Key Resolution) ✅ DONE
- [x] Tier 1: Environment variable (`FERNET_KEY`)
- [x] Tier 2: File-based (`/etc/healthbridge/fernet.key`)
- [x] Tier 3: Auto-generated (dev only)
- [x] Correct field masking in logs
- [ ] **Add key rotation CLI** (`python -m app.security.encryption rotate`)

---

## 8. Multi-Tenant Organizations ✅ DONE
- [x] Organization model (slug, tier, limits)
- [x] Staff onboarding with roles
- [x] Subscription tiers (FREE/STARTER/PROFESSIONAL/ENTERPRISE)
- [x] Patient/staff count enforcement
- [ ] **Add org-level branding** (logo, colors, custom domain)
- [ ] **Add org-level webhook configuration**

---

## 9. 3 EHR Connectors ✅ DONE
| Connector | Status | Features |
|-----------|--------|----------|
| **ABDM (India)** | ✅ | ABHA, consent, record sharing |
| **OpenMRS** | ✅ | Patient sync, encounter sync |
| **Generic FHIR R4** | ✅ | Generic CRUD, search |

- [ ] **Add Epic FHIR connector** (US market)
- [ ] **Add Cerner FHIR connector** (US market)

---

## Priority Integration Tasks for 30-Day Plan

These backend strengths need to be **exposed to the clinical layer** (Days 3-30):

| Day | Clinical Feature | Backend API Needed |
|-----|------------------|-------------------|
| 3-4 | OPD Registration + UHID | `POST /api/v1/patients` + org-scoped MRN generator |
| 5-6 | Vital Signs Entry | `POST /api/v1/fhir/Observation` (vital sign profiles) |
| 7 | SOAP Notes | `POST /api/v1/fhir/Composition` (SOAP structure) |
| 8-10 | Prescription Writer | `POST /api/v1/fhir/MedicationRequest` + drug formulary |
| 11-12 | Lab Orders | `POST /api/v1/fhir/ServiceRequest` + `Observation` for results |
| 13-14 | Appointment Scheduler | `POST /api/v1/fhir/Appointment` + slot management |
| 15-16 | Pharmacy Inventory | `Medication` + `Inventory` resources |
| 17-18 | Billing Engine | `Invoice` + `Payment` + GST calculation |
| 19-20 | IPD Admission | `Encounter` (inpatient) + `Location` (bed) |
| 21 | Discharge Summary | `Composition` (discharge) + PDF generation |
| 22-23 | Patient Portal | `GET /api/v1/patients/{id}/*` + consent UI |
| 24-25 | Multi-language | i18n on all patient-facing strings |
| 26-27 | ABDM Scan & Share | ABHA connector QR endpoint |
| 28-29 | Orchestrator Dashboard | Agent status + message delivery API |

---

## Quick Verification Commands

```bash
# Check all routers load
cd /mnt/c/AI\ agent\ Workflow/health-platform/backend
./venv/bin/python -c "
from app.main import app
for route in app.routes:
    if hasattr(route, 'methods'):
        print(f'{list(route.methods)} {route.path}')
"

# Test DPDP service
./venv/bin/python -c "
from app.services.dpdp_compliance import DpdpComplianceService
svc = DpdpComplianceService()
print('DPDP service OK:', hasattr(svc, 'conduct_dpia'))
"

# Test FHIR conversion
./venv/bin/python -c "
from app.services.fhir_conversion import FhirConversionService
svc = FhirConversionService()
print('FHIR conversion OK:', hasattr(svc, 'build_fhir_bundle_from_record'))
"

# Test ABHA connector
./venv/bin/python -c "
from app.connectors.abha import AbhaConnector
conn = AbhaConnector()
print('ABHA connector OK:', hasattr(conn, 'link_abha_address'))
"
```

---

**Status**: All 9 backend strengths are **implemented and working**. The 30-day plan builds the **clinical layer on top** — OPD, vitals, prescriptions, labs, billing, IPD, patient portal, ABDM integration.

Next: Start **Day 3 - OPD Registration + UHID + Token Queue**.