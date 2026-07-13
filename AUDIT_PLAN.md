# Health-Platform: Technical Audit & 30-Day Clinic-Ready Build Plan

**Source:** PDF audit document (Notes_260713_230329.pdf)  
**Extracted:** 2026-07-13  
**Repo:** github.com/19p1362/health-platform

---

## A. 10 CRITICAL/HIGH BUGS (Must Fix First)

| # | Bug | Location | Severity | Impact |
|---|-----|----------|----------|--------|
| 1 | `created_at`/`updated_at` use `default=datetime.utcnow` — evaluated once at import, not per-row | `models/__init__.py` | HIGH | All rows share identical timestamps |
| 2 | `handle_webhook()` called but never defined in `patient_intake.py` | Orchestrator | HIGH | Crashes if patient with missing data has phone |
| 3 | `admin.py` calls async `purge_audit_logs()` without `await` — silently does nothing | Backend | HIGH | Audit log purge is a no-op |
| 4 | `build_fhir_bundle_from_record()` referenced in `fhir.py` but never defined | Backend | HIGH | FHIR read endpoints crash |
| 5 | RBAC permission matrix missing `SUPER_ADMIN` — raises `ValueError` | `security/rbac.py` | HIGH | SUPER_ADMIN users can't perform any RBAC-checked action |
| 6 | `organizations.py` staff/patient counts always return 0 — broken SQL query | Backend | HIGH | Org stats always zero |
| 7 | (See PDF for #7-10) | | | |

---

## B. WHAT ALREADY EXISTS & WORKS WELL

### Backend Strengths
- 16 API routers fully wired in FastAPI (auth, patients, FHIR R4, consent, compliance, admin, ingestion, conversion, exports, connectors, organizations, WhatsApp)
- DPDP 2025 compliance — 2,716-line service module (consent, breach, erasure, cross-border)
- FHIR conversion — 2,757-line service (C-CDA ↔ FHIR, HL7V2 ↔ FHIR, FHIR ↔ PDF)
- Document ingestion pipeline — Aadhaar eKYC, photo/PDF → OCR (Tesseract) → AI extraction → FHIR R4 Bundle with OTC verification, XML decryption, SHA-256 hashing
- ABHA connector — 595-line module for Ayushman Bharat Health Account
- Audit trail — append-only, context-manager pattern, DPDP 1-year purge
- Fernet encryption — 3-tier key resolution (env → file → auto-gen), correct masking
- Multi-tenant organizations — full org onboarding with slug, subscription tiers, staff limits
- 3 EHR connectors — ABDM (India), OpenMRS (open-source), Generic FHIR R4

### Frontend Strengths
- 14 pages, 12 with full state handling (loading/error/empty/success)
- Polished dark theme — 1,719-line CSS with complete design system
- TanStack Query with 30s stale time, retry, no refetch on focus
- Export Center (705 lines) — full exports + EHR connector management UI
- Document Upload — drag-and-drop, image preview, 6 doc types, patient search, recent uploads

### Orchestrator Strengths
- 10 agents all execute end-to-end without exceptions (verified by `--migrate --seed --orchestrator --once`)
- Real FHIR endpoint calls to backend (`sync_from_healthbridge()`)
- 14-table SQLite schema with proper FKs, indexes, unique constraints (patients, meds, labs, appointments)
- Good code quality — type hints, docstrings, try/except on all DB and API calls

---

## C. WHAT'S MISSING (Prioritized)

### PO — Cannot Deploy Without
| Missing Item | Why | Effort |
|--------------|-----|--------|
| OPD Registration & Queue | Every clinic needs walk-in registration, UHID generation, token issuance | 2 days |
| Doctor Prescription Writer | Core clinical function — structured Rx with searchable drug formulary | 3 days |
| Pharmacy Inventory & Dispensing | Stock management, batch/expiry, dispense → inventory update | 3 days |
| Lab Test Management | Order tests, enter results with reference ranges, flag abnormals | 2 days |
| Billing & Payments | Invoice generation, GST, cash/UPI/card, receipt printing | 4 days |
| IPD Admission/Bed/Discharge | Bed assignment, admission formalities, discharge summary | 3 days |

### P1 — Needs Soon
| Missing Item | Why | Effort |
|--------------|-----|--------|
| Vital Signs Entry | BP/pulse/SpO₂/temp/RBS — nursing workflow | 1 day |
| SOAP Clinical Notes | Structured Subjective/Objective/Assessment/Plan | 1 day |
| Appointment Scheduler | Calendar view, phone booking, slot management | 2 days |
| Patient Portal | View records, upload docs, manage consent | 3 days |
| Multi-Language (Telugu, Hindi) | Hyderabad clinic staff speak Telugu | 2 days |
| Payment Gateway (UPI) | PhonePe/GPay/Paytm QR at counter | 1 day |

### P2 — Compliance & Scale
| Missing Item | Why | Effort |
|--------------|-----|--------|
| ABDM Scan & Share | Government mandate for 2026 — QR at reception | 2 days |
| Insurance/TPA Pre-auth | Cashless workflow for insured patients | 3 days |
| Government Schemes (Aarogyasri) | Telangana's flagship health scheme | 2 days |
| CGHS/ECHS Rate Cards | Govt employee health schemes | 2 days |
| NABH Clinical Audit | Random case review workflow | 2 days |
| Orchestrator Dashboard UI | Flask dashboard has empty static folder | 2 days |

### P3 — Polish
| Missing Item | Why | Effort |
|--------------|-----|--------|
| OT/Surgery Scheduling | Theatre booking, pre-op checklist | 3 days |
| PWA Offline Support | Indian internet reliability | 2 days |
| LIS Integration (specific machines) | Auto-import from Erba/Roche/Siemens | 3 days |
| Docker containers for all services | Production deployment | 1 day |
| E-prescription (ABDM push) | Push Rx to ABDM after patient consent | 1 day |

---

## D. ORCHESTRATOR-SPECIFIC GAPS

- Dashboard has no UI — `dashboard/static/` is empty, Flask 404s on load
- No real message delivery — 10 agents log to `communication_log` but nothing actually sends SMS/WhatsApp/email
- Security layer disconnected — auth, RBAC, encryption modules exist but dashboard API routes have zero middleware
- No insurance seed data — insurance agent always reports 0 claims in demo
- No Dockerfile — can't run orchestrator in docker-compose
- 0 test coverage — no unit tests for any agent module

---

## E. 30-DAY BUILD PLAN (Clinic-Ready)

### Week 1: Core Clinical (Days 1–7)
- **Day 1–2:** Fix all 10 CRITICAL/HIGH bugs (above)
- **Day 3–4:** OPD Registration + UHID + Token Queue
- **Day 5–6:** Vital Signs Entry (BP/Pulse/SpO₂/Temp/RBS)
- **Day 7:** SOAP Clinical Notes editor

### Week 2: Doctor Workflow (Days 8–14)
- **Day 8–10:** Prescription Writer (drug formulary, structured Rx)
- **Day 11–12:** Lab Order + Results Entry
- **Day 13–14:** Appointment Scheduler (slot calendar)

### Week 3: Financial (Days 15–21)
- **Day 15–16:** Pharmacy Inventory (batch, expiry, stock alerts)
- **Day 17–18:** Billing Engine (invoice, GST, cash/UPI/card)
- **Day 19–20:** IPD Admission + Bed Management
- **Day 21:** Discharge Summary (structured template + PDF)

### Week 4: Patient + Compliance (Days 22–30)
- **Day 22–23:** Patient Portal (login, view records, download reports)
- **Day 24–25:** Multi-language (react-i18next — Telugu first, then Hindi)
- **Day 26–27:** ABDM Scan & Share QR at reception
- **Day 28–29:** Orchestrator Dashboard UI + real message delivery
- **Day 30:** End-to-end integration test + production `.env` + Docker

> All this builds on top of what already works (auth, FHIR, compliance, audit, ingestion, export, connectors) — you're not rewriting, you're adding the clinical layer.

---

## F. HOW IT WORKS PROPERLY IN A HOSPITAL (The Real Flow)

A doctor or nurse using HealthBridge in a real clinic would need this 5-minute workflow:

1. **Patient walks in** → Reception: Search existing or register new → UHID generated → Token printed
2. **Nurse station:** Vital signs recorded (BP, pulse, temp, SpO₂, RBS)
3. **Doctor room:** Prescription written (searchable drug names, doses, instructions) → Orders lab tests if needed → Writes clinical notes (SOAP)
4. **Billing counter:** Bill generated from consultation + medicine + lab fees → Patient pays (cash/UPI/card)
5. **Pharmacy:** Prescription received → Drugs dispensed → Stock updated
6. **Lab:** Sample collected → Results entered → Flagged abnormals
7. **Exit:** Patient leaves with medicines, lab token, and prescription copy

**HealthBridge today handles Step 0 only (patient exists in DB). The entire 5-minute flow is missing.**

---

## Bottom Line

You have a technically impressive foundation — FHIR R4, DPDP compliance, ABDM connector, AI orchestrator agents, audit trails, document ingestion. What's missing is **every single floor-level hospital workflow** that a doctor/nurse/receptionist/pharmacist touches daily.

**With 30 days of focused build, you can go from a backend demo to a clinic-usable system.**

---

**Extracted from:** `Notes_260713_230329.pdf` (12 pages)  
**Date:** 2026-07-13