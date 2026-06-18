# HealthBridge Platform

**Healthcare Data Orchestration Platform — From Paper Records to AI-Powered Patient Care**

<p align="center">
  <img src="https://img.shields.io/badge/FHIR-R4-22d3ee?style=flat-square" alt="FHIR R4"/>
  <img src="https://img.shields.io/badge/DPDP_2025-Compliant-34d399?style=flat-square" alt="DPDP 2025 Compliant"/>
  <img src="https://img.shields.io/badge/ABDM-Ready-a78bfa?style=flat-square" alt="ABDM Ready"/>
  <img src="https://img.shields.io/badge/Multi_Tenant-SaaS-fbbf24?style=flat-square" alt="Multi-Tenant SaaS"/>
  <img src="https://img.shields.io/badge/Python_3.12+-4ade80?style=flat-square" alt="Python 3.12+"/>
  <img src="https://img.shields.io/badge/React_18+-60a5fa?style=flat-square" alt="React 18+"/>
</p>

---

A unified healthcare automation platform that solves the biggest problem in Indian healthcare: **paper-based patient data never reaches the doctors, nurses, or care coordinators who need it.**

| Layer | What it does | How |
|-------|-------------|-----|
| **Document Ingestion & API** | Takes photos and PDFs of prescriptions, lab reports, and discharge summaries → converts them to structured digital health records (FHIR R4) | OCR + AI extraction → FHIR API |
| **AI Care Orchestration** | 10 autonomous agents that monitor patients 24/7 — track medications, follow-ups, appointments, lab results, risk scores, insurance claims | Agent loop + SQLite DB + Flask dashboard |
| **Multi-Tenant SaaS** | One platform serving multiple clinics/hospitals with complete data isolation | Organization model + tenant-scoped JWT |

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        HEALTHBRIDGE PLATFORM                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐     │
│  │  React SPA   │    │  FastAPI     │    │  10 AI Agents    │     │
│  │  (Vite+TS)   │◄──►│  Backend     │◄──►│  (Orchestrator)  │     │
│  │  Port 3001   │    │  Port 8080   │    │  Port 5000       │     │
│  └──────────────┘    └──────┬───────┘    └──────────────────┘     │
│                             │                                      │
│                    ┌────────┴────────┐                             │
│                    │   SQLite / PG   │                             │
│                    │   (FHIR Data)   │                             │
│                    └─────────────────┘                             │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Multi-Tenant Layer                         │  │
│  │  Organization → Users → Patients (tenant_id on every row)    │  │
│  │  JWT carries tenant_id → auto-filtered queries               │  │
│  │  Subscription tiers: Free / Starter / Professional / Ent.    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │  ABDM/ABHA   │  │  DPDP 2025   │  │  WhatsApp Bridge       │   │
│  │  Integration │  │  Compliance  │  │  (E2EE patient comms)  │   │
│  └──────────────┘  └──────────────┘  └────────────────────────┘   │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## The Problem This Solves

Most Indian hospitals and clinics don't use Electronic Health Records (EHRs). Patient data exists as:

- Handwritten prescriptions on paper
- Printed lab reports
- WhatsApp photos of pharmacy bills
- Discharge summaries as scanned PDFs

**HealthBridge ingests all of this** → turns it into structured FHIR R4 patient records → then 10 AI agents automatically track medication adherence, overdue follow-ups, abnormal lab results, appointment reminders, risk scores, insurance claims, and more.

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
| All unified | http://localhost:3001 | Single entry point (frontend proxies API/docs) |

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

## Multi-Tenant SaaS Features

HealthBridge is built as a **multi-tenant platform** from the ground up:

- **Organizations**: Each clinic/hospital is a separate tenant with isolated data
- **Role-based access**: SUPER_ADMIN, ORG_ADMIN, DOCTOR, NURSE, COORDINATOR, READ_ONLY
- **Subscription tiers**: Free (100 patients, 5 staff), Starter (1K, 15), Professional (10K, 50), Enterprise (unlimited)
- **Staff management**: Invite team members, assign roles, deactivate
- **Signup flow**: 3-step wizard → organization + admin created instantly

### Signup

```bash
curl -X POST http://localhost:8080/api/v1/organizations/register \
  -H "Content-Type: application/json" \
  -d '{
    "organization_name": "Your Clinic",
    "admin_email": "doctor@clinic.com",
    "admin_password": "yourpassword",
    "admin_full_name": "Dr. Name"
  }'
```

## API Reference

### Authentication & Organizations

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/v1/organizations/register` | **Create org + admin user (SaaS signup)** |
| `GET` | `/api/v1/organizations/me` | Get current organization details |
| `PUT` | `/api/v1/organizations/me` | Update organization |
| `GET` | `/api/v1/organizations/me/staff` | List staff members |
| `POST` | `/api/v1/organizations/me/invite` | Invite new staff member |
| `PUT` | `/api/v1/organizations/me/staff/{id}/deactivate` | Deactivate staff |
| `POST` | `/api/v1/auth/login` | Get JWT token |
| `POST` | `/api/v1/auth/register` | Create user account |
| `POST` | `/api/v1/auth/refresh` | Refresh token |

### Patients & FHIR

| Method | Path | What it does |
|--------|------|-------------|
| `GET` | `/api/v1/patients` | List / search patients (tenant-scoped) |
| `POST` | `/api/v1/patients` | Create patient record |
| `GET` | `/api/v1/patients/{id}` | Get patient details |
| `GET` | `/api/v1/fhir/{resource_type}` | FHIR R4 resource search |
| `GET` | `/api/v1/fhir/{resource_type}/{id}` | Read FHIR resource |

### Document Ingestion

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/v1/ingest/upload` | **Upload document** (photo/PDF → OCR → AI → FHIR) |
| `GET` | `/api/v1/ingest/types` | List supported document types |
| `GET` | `/api/v1/ingest/logs` | View ingestion history |

### Compliance (DPDP 2025)

| Method | Path | What it does |
|--------|------|-------------|
| `GET` | `/api/v1/compliance/breaches` | List data breaches |
| `POST` | `/api/v1/compliance/breaches/report` | Report a breach |
| `GET` | `/api/v1/compliance/audit-log` | View audit logs |
| `GET` | `/api/v1/compliance/report` | Compliance report |

Interactive docs: **http://localhost:8080/docs**

## 10 AI Care Agents

| # | Agent | Frequency | What it does |
|---|-------|-----------|-------------|
| 1 | Patient Intake | 60 min | Onboard new patients, fill missing data |
| 2 | Medication Adherence | 15 min | Track missed doses, send reminders |
| 3 | Follow-Up | 30 min | Escalate overdue follow-ups |
| 4 | Appointment | 30 min | Appointment reminders |
| 5 | Risk Prediction | 60 min | Score patients LOW/MEDIUM/HIGH/CRITICAL |
| 6 | Family Care | 7 days | Weekly care summaries |
| 7 | Voice Care | 60 min | Voice call eligibility |
| 8 | Pharmacy | 60 min | Refill alerts |
| 9 | Lab | 30 min | Abnormal lab alerts |
| 10 | Insurance | 24 h | Stalled claims flagging |

## Security & DPDP 2025 Compliance

Built for **India's Digital Personal Data Protection Act 2025**:

| Requirement | Implementation |
|------------|---------------|
| Consent management | Granular purpose + expiry per consent record |
| Data retention | Clinical: 3 years, General: 1 year |
| Erasure notification | Within 48 hours |
| Breach notification | SLA-tracked with audit trail |
| Grievance redressal | 90-day SLA |
| Encryption at rest | Fernet on patient PHI fields |
| Audit logging | Every access logged with user ID + timestamp |
| E2EE communication | WhatsApp Business App (manual relay, NOT Twilio/Meta API) |

**Why no Twilio?** Twilio's WhatsApp API can decrypt message contents, violating DPDP 2025 for health data. We use the WhatsApp Business App on a dedicated smartphone for true end-to-end encryption.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI, SQLAlchemy Async, Uvicorn |
| **Database** | SQLite (dev), PostgreSQL (production) |
| **Cache** | Redis |
| **Frontend** | React 18, TypeScript, Vite, React Router |
| **AI Agents** | Python, APScheduler, SQLite |
| **Compliance** | DPDP 2025, FHIR R4, ICD-10, SNOMED-CT India |
| **Integration** | ABDM (ABHA), WhatsApp Business, Aadhaar eKYC |
| **Container** | Docker, Docker Compose |

## Project Structure

```
health-platform/
├── backend/                  FHIR API + Document Ingestion
│   ├── app/
│   │   ├── api/              REST endpoints (auth, patients, fhir, orgs…)
│   │   ├── services/         OCR pipeline, FHIR conversion, DPDP compliance
│   │   ├── security/         JWT, tenant isolation, RBAC, encryption, audit
│   │   ├── models/           SQLAlchemy tables (Organization, User, Patient…)
│   │   ├── static/           Landing page
│   │   ├── config.py         All settings via environment variables
│   │   ├── database.py       Async SQLAlchemy (SQLite + PostgreSQL)
│   │   └── main.py           FastAPI entry point
│   ├── requirements.txt
│   └── Dockerfile
├── orchestrator/             10 AI Care Agents
│   ├── agents/               10 agent modules
│   ├── dashboard/            Flask UI at port 5000
│   ├── master_orchestrator.py
│   └── run.py
├── frontend/                 React SPA (Vite + TypeScript)
│   ├── src/pages/            13 page views (Landing, Login, Signup, Dashboard…)
│   └── vite.config.ts
├── docker-compose.yml        PostgreSQL, Redis, MinIO
└── package.json              One-command start
```

## Docker (Production)

```bash
docker compose up -d
```

Starts: API (port 8080), Frontend (port 3000), PostgreSQL, Redis, MinIO.

---

<p align="center">
  <i>HealthBridge Platform — Made in India · DPDP 2025 Compliant · ABDM Integrated</i>
</p>
