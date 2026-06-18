# HealthBridge Platform

<div align="center">
  <h3>Healthcare Data Orchestration · FHIR R4 · DPDP 2025 Compliant</h3>
  <p><b>Phase 1:</b> Document Ingestion & FHIR API · <b>Phase 2:</b> 10-Agent Care Orchestration</p>
</div>

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     HealthBridge Platform                        │
├──────────────────────┬──────────────────────────────────────────┤
│    Phase 1: API      │     Phase 2: Orchestration              │
│                      │                                          │
│  Photo/PDF → OCR     │  Patient Intake Agent                   │
│  → AI Extraction     │  Medication Adherence Agent             │
│  → FHIR R4 Bundle    │  Follow-Up Agent (escalation)           │
│  → Patient Records   │  Appointment Agent                      │
│                      │  Risk Prediction Agent                  │
│  ─── API Endpoints   │  Family Care Agent                      │
│  Auth · Patients     │  Voice Care Agent                       │
│  FHIR · Conversion   │  Pharmacy Agent                         │
│  Consent · Admin     │  Lab Agent                              │
│  Compliance · DPDP   │  Insurance Agent                        │
│  Document Ingestion  │                                          │
│  ABHA · Aadhaar      │  ─── Orchestrator Dashboard             │
│                      │      Flask UI · Agent Logs · Stats      │
├──────────────────────┴──────────────────────────────────────────┤
│                    Frontend (React SPA)                         │
│      Patient Search · FHIR Explorer · Document Upload          │
│      Consent Manager · Compliance Dashboard · Audit Logs       │
│      Conversion Tools · Settings · Patient Chart                │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
health-platform/
├── backend/                    # Phase 1: FastAPI FHIR & ingestion API
│   ├── app/
│   │   ├── api/               # REST routes (auth, patients, fhir, consent…)
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── security/          # Auth, RBAC, encryption, audit
│   │   ├── services/          # FHIR, DPDP, ABHA, Aadhaar, OCR, WhatsApp
│   │   ├── static/            # Branded landing page + JS SPA
│   │   ├── utils/
│   │   ├── config.py          # Pydantic settings (env-based)
│   │   ├── database.py        # Async SQLAlchemy engine
│   │   └── main.py            # FastAPI entry point
│   ├── data/                  # SQLite DB + uploads
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── orchestrator/               # Phase 2: 10-Agent care orchestration
│   ├── agents/                # 10 autonomous agent modules
│   │   ├── patient_intake.py
│   │   ├── medication_adherence.py
│   │   ├── follow_up.py
│   │   ├── appointment.py
│   │   ├── risk_prediction.py
│   │   ├── family_care.py
│   │   ├── voice_care.py
│   │   ├── pharmacy.py
│   │   ├── lab.py
│   │   └── insurance.py
│   ├── communication/
│   │   └── email.py           # SMTP sender (graceful degradation)
│   ├── dashboard/             # Flask agent orchestration UI
│   │   └── server.py
│   ├── security/              # JWT auth, Fernet encryption, RBAC
│   ├── config.py              # Orchestrator config (env-based)
│   ├── db_adapter.py          # Sync SQLite database (17 tables)
│   ├── master_orchestrator.py # Priority scheduler
│   └── run.py                 # Unified CLI entry point
│
├── frontend/                   # React SPA (Vite + TypeScript)
│   ├── src/
│   │   ├── components/        # Layout, ProtectedRoute
│   │   ├── hooks/             # useAuth
│   │   ├── pages/             # 11 page views
│   │   └── services/          # API client
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
│
├── .github/workflows/ci.yml   # CI/CD pipeline
├── .env.example                # All environment variables
├── .gitignore
├── docker-compose.yml          # PostgreSQL + Redis + MinIO
├── package.json                # Root: one-command start
├── README.md
└── example_workflow.py         # E2E workflow example
```

## Quick Start

### Prerequisites
- Python 3.12+, Node.js 20+, npm
- Tesseract OCR (for document ingestion): `apt install tesseract-ocr tesseract-ocr-hin`
- Poppler utils (for scanned PDFs): `apt install poppler-utils`

### One-Command Start (Backend + Frontend)
```bash
npm install
npm start
```
This starts the FastAPI backend on **port 8080** and the React frontend on **port 3001**.

### Run the Orchestrator (separate terminal)
```bash
cd orchestrator
pip install -r ../backend/requirements.txt  # shared deps
python run.py                               # migrate + seed + dashboard + agents
```
Orchestrator dashboard: **port 5000** (Flask UI)

### Run Orchestrator Components Individually
```bash
cd orchestrator
python run.py --migrate         # Create database tables
python run.py --seed            # Seed sample data (5 patients)
python run.py --dashboard       # Flask dashboard only
python run.py --orchestrator    # Continuous agent loop
python run.py --orchestrator --once  # Run all agents once & exit
```

## API Overview (Backend — port 8080)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login (JWT) |
| POST | `/api/v1/auth/refresh` | Refresh token |
| GET | `/api/v1/patients` | List/search patients |
| POST | `/api/v1/patients` | Create patient |
| GET | `/api/v1/patients/{id}` | Get patient details |
| GET | `/api/v1/patients/{id}/medical-record` | Medical record |
| GET | `/api/v1/fhir/Patient` | FHIR Patient search |
| POST | `/api/v1/fhir/$everything` | FHIR everything bundle |
| POST | `/api/v1/conversion/ccda-to-fhir` | C-CDA → FHIR |
| POST | `/api/v1/consent` | Create consent record |
| GET | `/api/v1/compliance/breach-log` | DPDP breach log |
| POST | `/api/v1/ingest/upload` | Upload document (OCR → AI → FHIR) |
| GET | `/health` | Health check |

Full API docs at **`http://localhost:8080/docs`** (Swagger UI).

## Agent System (Orchestrator)

10 agents run in priority order, each with a configurable interval:

| Priority | Agent | Interval | Description |
|----------|-------|----------|-------------|
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

### Agent Interface
Every agent exposes a single `run(db: Database) -> dict` function. The orchestrator passes a `Database()` instance with synchronous SQLite access. All agents return integer counters — no side effects other than database writes.

## Document Ingestion Pipeline

```
Upload (photo/PDF) → pdfplumber/OCR (Tesseract EN+HIN)
  → AI Extraction (LLM) → Structured JSON
    → FHIR R4 Bundle (Patient + Condition + MedicationRequest + Observation)
```

- Supports: JPEG, PNG, WebP, TIFF, PDF (text + scanned)
- Mock AI extraction works without API key (keyword-based)
- AI extraction via OpenAI-compatible API

## Security & Compliance

### DPDP 2025 Compliance
- Consent management with granular purpose/expiry
- Data retention policies (clinical: 3 years, general: 1 year)
- Erasure notification within 48 hours
- Breach notification with SLA tracking
- Grievance redressal within 90 days
- Audit logging for every data access
- Fernet encryption at rest (patient PHI fields)

### Authentication
- JWT-based auth (access + refresh tokens)
- bcrypt password hashing (pinned bcrypt==4.2.1)
- Role-based access control (admin, doctor, nurse, coordinator)
- Rate limiting (100/min, 1000/hour)

### E2EE Communication
- **No Twilio, no Meta Cloud API** — these break E2EE
- WhatsApp Business App on a dedicated phone (true E2EE)
- Secure patient portal (HTTPS + Fernet encryption)
- Email for non-PHI reminders only

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
# Edit .env with your settings
```

Key variables:
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./healthbridge.db` | DB connection (SQLite for dev) |
| `SECRET_KEY` | `change-me-in-production` | App secret |
| `JWT_SECRET` | `change-me-in-production` | JWT signing key |
| `ENCRYPTION_KEY` | (auto-generated) | Fernet 32-byte base64 key |
| `AI_EXTRACTION_API_KEY` | (empty = mock) | OpenAI API key for document extraction |

## Docker Deployment

```bash
docker compose up -d
```

Starts: API (8080), PostgreSQL, Redis, MinIO (dev), pgAdmin (dev).

## CI/CD

GitHub Actions workflow runs:
- Backend lint (ruff) + tests (pytest)
- Frontend build
- Security scan (Trivy + pip audit + npm audit)
- Docker build & push to GHCR (on main)
- Deploy via SSH (on main)

## License

MIT
