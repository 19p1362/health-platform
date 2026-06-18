# HealthBridge Platform

**Healthcare Data Orchestration Platform — From Paper Records to AI-Powered Patient Care**

A unified healthcare automation system that solves the biggest problem in Indian healthcare: **paper-based patient data never reaches the doctors, nurses, or care coordinators who need it.**

This platform does two things in one repo:

| Phase | What it does | How |
|-------|-------------|-----|
| **Phase 1 — Document Ingestion & API** | Takes photos and PDFs of prescriptions, lab reports, and discharge summaries → converts them to structured digital health records (FHIR R4) | OCR + AI extraction → FHIR API |
| **Phase 2 — AI Care Orchestration** | 10 autonomous agents that monitor patients 24/7 — track medications, follow-ups, appointments, lab results, risk scores, insurance claims | Agent loop + SQLite DB + Flask dashboard |

---

## The Problem This Solves

Most Indian hospitals and clinics don't use Electronic Health Records (EHRs). Patient data exists as:
- Handwritten prescriptions on paper
- Printed lab reports
- WhatsApp photos of pharmacy bills
- Discharge summaries as scanned PDFs

**HealthBridge ingests all of this** → turns it into structured FHIR R4 patient records → then 10 AI agents automatically track medication adherence, overdue follow-ups, abnormal lab results, appointment reminders, risk scores, insurance claims, and more.

---

## Quick Start

### 1. Backend + Frontend (the API and web dashboard)

```bash
cd /mnt/c/AI\ agent\ Workflow/health-platform
npm install
npm start
```

| Service | URL | What it is |
|---------|-----|-----------|
| FastAPI Backend | http://localhost:8080 | FHIR API, auth, ingestion, compliance |
| Swagger Docs | http://localhost:8080/docs | Interactive API browser |
| React Frontend | http://localhost:3001 | Full SPA: patients, FHIR explorer, upload, compliance |
| Landing Page | http://localhost:8080 | Branded portal with live API docs link |

### 2. AI Orchestrator (the agents — run in a separate terminal)

```bash
cd orchestrator
pip install -r ../backend/requirements.txt
python run.py               # starts everything: migrate + seed + dashboard + agents
```

| Component | Default | Description |
|-----------|---------|-------------|
| Flask Dashboard | http://localhost:5000 | Agent status, patient stats, activity feed |
| Agent Loop | Background | Runs 10 agents on schedule (continuous) |
| SQLite DB | `orchestrator/` | Local database for agent operations |

### 3. Try it out — run all agents once

```bash
cd orchestrator
python run.py --orchestrator --once
```

This runs all 10 agents a single time and prints their results — no continuous loop.

---

## Project Structure

```
health-platform/
│
├── backend/                        ◄── Phase 1: FHIR API + Document Ingestion
│   ├── app/
│   │   ├── api/                    REST endpoints (auth, patients, fhir, consent…)
│   │   ├── services/               OCR pipeline, FHIR conversion, DPDP compliance
│   │   ├── security/               JWT, bcrypt, RBAC, Fernet encryption, audit
│   │   ├── models/                 SQLAlchemy tables
│   │   ├── static/                 Branded landing page at /
│   │   ├── config.py               All settings via environment variables
│   │   ├── database.py             Async SQLAlchemy (works with SQLite + PostgreSQL)
│   │   └── main.py                 FastAPI entry point (registers all routers)
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── orchestrator/                   ◄── Phase 2: 10 AI Care Agents
│   ├── agents/                     One Python file per agent
│   │   ├── patient_intake.py           # Onboard new patients, fill missing data
│   │   ├── medication_adherence.py     # Track missed doses, send reminders
│   │   ├── follow_up.py                # Escalate overdue follow-ups
│   │   ├── appointment.py              # Appointment reminders
│   │   ├── risk_prediction.py          # Score patients LOW/MEDIUM/HIGH/CRITICAL
│   │   ├── family_care.py              # Weekly care summaries
│   │   ├── voice_care.py               # Voice call eligibility
│   │   ├── pharmacy.py                 # Refill alerts
│   │   ├── lab.py                      # Abnormal lab alerts
│   │   └── insurance.py                # Stalled claims flagging
│   ├── dashboard/                  Flask UI at port 5000 (agent logs, stats)
│   ├── communication/              Email sender (SMTP, graceful degradation)
│   ├── security/                   Auth + encryption for the agent layer
│   ├── config.py                   Agent intervals, priority, thresholds
│   ├── db_adapter.py               Sync SQLite (17 tables) — agents write here
│   ├── master_orchestrator.py      Priority scheduler that runs agents
│   └── run.py                      Unified CLI (migrate, seed, dashboard, agents)
│
├── frontend/                       ◄── React SPA (Vite + TypeScript)
│   ├── src/pages/                  11 page views (Dashboard, PatientSearch, FHIR…)
│   ├── src/components/             Layout, ProtectedRoute
│   ├── src/hooks/                  useAuth
│   ├── src/services/               API client
│   └── vite.config.ts
│
├── .github/workflows/ci.yml        Tests: backend + orchestrator + frontend
├── docker-compose.yml              PostgreSQL, Redis, MinIO (for production)
├── package.json                    One-command start (`npm start`)
├── .env.example                    All environment variables with descriptions
└── README.md                       This file
```

---

## Data Flow: End to End

```
Patient visits clinic
        │
        ▼
Paper prescription / lab report / discharge summary
        │
        ▼ (clinic staff)
WhatsApp Business App on dedicated phone (E2EE encrypted)
  → Staff downloads photo
  → Uploads to HealthBridge ingestion API
        │
        ▼
POST /api/v1/ingest/upload
        │
        ├─ PDF?  → pdfplumber (text) or pdf2image + Tesseract OCR (scanned)
        ├─ Photo? → Tesseract OCR (English + Hindi)
        │
        ▼
AI Extraction (OpenAI-compatible API or built-in mock)
  → Structured JSON: patient info, diagnosis, medicines, lab results
        │
        ▼
FHIR R4 Bundle
  → Patient, Condition, MedicationRequest, Observation resources
        │
        ▼
Patient records stored in database
        │
        ▼  (sync_from_healthbridge every cycle)
Orchestrator agents pick up the new data
        │
        ├─ Medication Adherence → tracks daily doses, flags missed
        ├─ Follow-Up            → escalates overdue (1d=reminder, 3d=urgent, 7d=critical)
        ├─ Risk Prediction      → scores LOW/MEDIUM/HIGH/CRITICAL
        ├─ Pharmacy             → flags approaching refill
        ├─ Lab                  → flags abnormal results
        └─ Insurance            → finds stalled claims
```

---

## Agent System Details

The 10 agents run in priority order with configurable intervals:

| # | Agent | Runs every | What it does | When to check |
|---|-------|-----------|-------------|---------------|
| 1 | Patient Intake | 60 min | Finds patients missing phone/address → logs outreach | First run after sync |
| 2 | Medication Adherence | 15 min | Checks adherence_log for missed doses → sends reminders | After patient has meds |
| 3 | Follow-Up | 30 min | Finds overdue follow-ups → escalates (reminder→urgent→critical) | Ongoing |
| 4 | Appointment | 30 min | Finds today/tomorrow appointments → marks notified | Daily |
| 5 | Risk Prediction | 60 min | Scores every patient (missed meds + overdue fups + abnormal labs) | After agents 2-4 run |
| 6 | Family Care | 7 days | Generates weekly summaries for family members | Weekly |
| 7 | Voice Care | 60 min | Identifies high-risk patients without WhatsApp response | After risk scoring |
| 8 | Pharmacy | 60 min | Flags medications near refill threshold | Ongoing |
| 9 | Lab | 30 min | Flags abnormal lab results → logs notification | After labs synced |
| 10 | Insurance | 24 h | Finds stalled claims → flags for coordinator | Daily |

Every agent returns the same structure: `{"errors": 0, "patients_contacted": 5, …}` — integer counters. No side effects other than database writes.

---

## API Reference

The backend runs on port 8080 and provides these endpoints:

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/v1/auth/register` | Create a new user account |
| `POST` | `/api/v1/auth/login` | Get JWT token (email + password) |
| `POST` | `/api/v1/auth/refresh` | Refresh an expiring token |
| | |
| `GET` | `/api/v1/patients` | List / search patients |
| `POST` | `/api/v1/patients` | Create a new patient record |
| `GET` | `/api/v1/patients/{id}` | Get patient details |
| `GET` | `/api/v1/patients/{id}/medical-record` | Get full medical record |
| | |
| `GET` | `/api/v1/fhir/Patient` | FHIR R4 Patient search |
| `POST` | `/api/v1/fhir/$everything` | FHIR $everything bundle |
| | |
| `POST` | `/api/v1/conversion/ccda-to-fhir` | Convert C-CDA XML → FHIR |
| `POST` | `/api/v1/consent` | Create DPDP consent record |
| `GET` | `/api/v1/compliance/breach-log` | View DPDP breach notifications |
| | |
| `POST` | `/api/v1/ingest/upload` | **Upload document** (photo/PDF → OCR → AI → FHIR) |
| `GET` | `/api/v1/ingest/types` | List supported document types |
| `GET` | `/api/v1/ingest/logs` | View ingestion history |
| | |
| `GET` | `/health` | Health check (returns status + version + DPDP flag) |

Interactive docs: **http://localhost:8080/docs**

---

## Security & DPDP 2025 Compliance

This platform is designed for **India's Digital Personal Data Protection Act 2025**:

| Requirement | Implementation |
|------------|---------------|
| Consent management | Granular purpose + expiry per consent record |
| Data retention | Clinical records: 3 years, General: 1 year |
| Erasure notification | Within 48 hours of request |
| Breach notification | SLA-tracked with audit trail |
| Grievance redressal | 90-day SLA |
| Encryption at rest | Fernet encryption on patient PHI fields |
| Audit logging | Every data access logged with user ID + timestamp |
| E2EE communication | WhatsApp Business App (manual relay), NOT Twilio/Meta API |

**Why no Twilio?** Twilio's WhatsApp API can decrypt message contents, which violates DPDP 2025 for health data. We use the WhatsApp Business App on a dedicated smartphone — this preserves true end-to-end encryption. Staff manually forwards patient photos. Email is used for non-PHI reminders only.

---

## Docker (for production deployment)

```bash
docker compose up -d
```

Starts: API (port 8080), PostgreSQL, Redis, MinIO (dev file storage), pgAdmin (port 5050).

---

## CI/CD

Every push to `main` triggers:

1. **Backend** — ruff lint + pytest (with PostgreSQL service)
2. **Orchestrator** — migrate + seed + run all agents once (smoke test)
3. **Frontend** — npm install + build
4. **Security scan** — Trivy + pip audit + npm audit
5. **Docker build** — Build & push `-backend` and `-frontend` images to GHCR
6. **Deploy** — SSH to VPS, pull images, docker compose up

---

## License

MIT

---

## What Was Merged

This repo unifies two previously separate projects:

- **HealthBridge** (github.com/19p1362/HealthBridge) → `backend/` + `frontend/`
- **HealthcareOrchestra** (github.com/19p1362/HealthcareOrchestra) → `orchestrator/`

Both old repos are now stale and will be deleted.
