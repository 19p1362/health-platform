# Health-Platform: 30-Day Clinical-Ready Build Plan

**Target:** Production-ready for Indian clinics (ABDM, DPDP 2025 compliant)  
**Stack:** FastAPI backend (port 8080) + React SPA (port 3001) + 10-Agent Orchestrator  
**Current State:** Day 2 complete (startup fixes, frontend build, env config)  
**Moat:** Photo/PDF → OCR → FHIR R4 pipeline via E2EE WhatsApp (Business App, no Twilio for PHI)

---

## Phase 1: Foundation & Compliance (Days 3-Ready Core) — Days 3–10

### Day 3: Auth & RBAC Hardening
- **Fix UserRole enum mismatch** — `SUPER_ADMIN/ORG_ADMIN/DOCTOR/NURSE/COORDINATOR/READ_ONLY` vs RBAC matrix using `ADMIN` (non-existent)
- Implement `SUPER_ADMIN` → full access, `ORG_ADMIN` → org-scoped admin, `DOCTOR` → clinical write, `NURSE` → clinical read/write own, `COORDINATOR` → workflow management
- Update `auth.register` to use valid roles
- Add JWT refresh token rotation (15min access / 7d refresh)
- **Deliverable:** Zero RBAC gaps, all roles mapped to permissions

### Day 4: DPDP 2025 Consent Engine
- Consent artefact creation (digital signature, timestamp, purpose-bound)
- Consent withdrawal flow with audit trail
- Data principal rights API: access, correction, erasure, portability
- 30-day grace period enforcement (already in `dpdp_compliance.py:632`)
- **Deliverable:** `/api/v1/consent/*` endpoints passing DPDP audit checklist

### Day 5: ABDM Integration — Core
- ABHA number verification (Aadhaar/OVD)
- Health ID linking to patient resource
- Health Facility Registry (HFR) sync for org onboarding
- Health Professional Registry (HPR) for doctor onboarding
- **Deliverable:** `/api/v1/abdm/*` — verify, link, facility/register, professional/register

### Day 6: FHIR R4 Resource Completeness
- Implement missing profiles: `Patient`, `Observation`, `Condition`, `MedicationRequest`, `Encounter`, `DiagnosticReport`, `Immunization`, `ServiceRequest`
- Search parameters: `_id`, `patient`, `date`, `code`, `category`, `status`
- Bundle transaction support for batch uploads
- Validate against HL7 FHIR validator
- **Deliverable:** FHIR R4 conformance statement + 100% profile coverage

### Day 7: Document Ingestion Pipeline (Moat)
- WhatsApp Business App webhook (E2EE, no Twilio)
- Media download → virus scan → OCR (Tesseract + PaddleOCR for Indic)
- Structured extraction → FHIR mapping (Observation, DiagnosticReport, MedicationRequest)
- Deduplication via content hash
- Human-in-the-loop review queue for low-confidence extractions
- **Deliverable:** Photo/PDF → FHIR in <30s, review UI for clinicians

### Day 8: Multi-Tenant SaaS Foundation
- Organization isolation (row-level security via `org_id` on all tables)
- Subscription tiers: Free (1 clinic), Pro (5 clinics), Enterprise (unlimited)
- Feature flags per tier (ABDM, WhatsApp, Analytics, API access)
- Usage metering (API calls, storage, agents)
- **Deliverable:** `organizations` router + middleware + billing webhook stubs

### Day 9: Audit & Security Hardening
- Immutable audit log (append-only table, signed entries)
- Encryption at rest: AES-256-GCM for PHI columns
- Field-level encryption for: `patient.identifier`, `observation.value`, `document.content`
- Rate limiting per org + per user
- CORS, CSP, HSTS, security headers
- **Deliverable:** Security audit report (OWASP Top 10 pass)

### Day 10: Testing & CI/CD Pipeline
- Unit tests: ≥80% coverage (pytest, pytest-asyncio)
- Integration tests: FastAPI TestClient + testcontainers (PostgreSQL, Redis)
- Contract tests: FHIR + ABDM API schemas
- GitHub Actions: lint → test → build → docker push → deploy staging
- Staging environment: `staging.healthplatform.in` (Cloudflare Tunnel)
- **Deliverable:** Green CI on every PR, staging auto-deploy

---

## Phase 2: 10-Agent Care Orchestration (Days 11–20)

### Day 11: Master Orchestrator & Agent Framework
- Refactor `master_orchestrator.py`: pluggable agent registry, event bus (Redis Streams)
- Agent lifecycle: init → health-check → process → emit events → shutdown
- Structured logging (JSON) + correlation IDs across agents
- **Deliverable:** `orchestrator run --agent=<name>` works for all 10 agents

### Day 12: Agent 1 — Patient Intake
- WhatsApp-driven onboarding flow (ABHA verify → demographics → consent)
- Chief complaint capture → structured `Encounter` creation
- Triage scoring (ESI-like) → queue priority
- **Deliverable:** End-to-end intake via WhatsApp, creates FHIR Encounter

### Day 13: Agent 2 — Appointment Scheduling
- Slot management (doctor × clinic × duration)
- Patient self-booking via WhatsApp buttons
- Reminder cascade: 24h / 2h / 10min (WhatsApp + SMS fallback)
- No-show detection → auto-rebook + waitlist promotion
- **Deliverable:** Booking API + WhatsApp flow, calendar sync (CalDAV)

### Day 14: Agent 3 — Follow-Up Engine
- Rule-based follow-up triggers (post-visit, lab review, chronic care)
- Configurable protocols per condition (HTN, DM, ANC, etc.)
- Escalation ladder: patient → nurse → doctor → coordinator
- **Deliverable:** Follow-up dashboard + automated outreach

### Day 15: Agent 4 — Medication Adherence
- Prescription parsing → `MedicationRequest` + `MedicationStatement`
- Dose schedule generation → WhatsApp reminders
- Adherence tracking (patient-reported + pharmacy refill data)
- Missed-dose alerts to care team
- **Deliverable:** Adherence dashboard per patient/org

### Day 16: Agent 5 — Lab Integration
- Lab order creation (`ServiceRequest`) → sample collection tracking
- Result ingestion (HL7 v2 / PDF OCR / API) → `DiagnosticReport`
- Critical value auto-alert (WhatsApp + in-app)
- Trend visualization (Observation time-series)
- **Deliverable:** Lab order → result flow, critical alerts <5min

### Day 17: Agent 6 — Risk Prediction
- Rule engine (ICD-10 + lab trends + vitals) for: sepsis, AKI, readmission, fall risk
- ML model serving (ONNX Runtime) for chronic disease progression
- Explainable outputs (SHAP) for clinician trust
- **Deliverable:** Risk scores on patient dashboard, alerting rules

### Day 18: Agent 7 — Insurance & Claims
- ABDM-compliant claim bundle (Composition + Claim + ClaimResponse)
- Pre-authorization workflow
- Denial management with auto-appeal drafting
- Payer integration stubs (PMJAY, ESI, private)
- **Deliverable:** Claim submission + status tracking

### Day 19: Agent 8 — Family Care Coordinator
- Household linking (ABHA family IDs)
- Care plan sharing (consent-gated)
- Pediatric / geriatric specific workflows (immunization, fall prevention)
- Caregiver notifications (separate WhatsApp opt-in)
- **Deliverable:** Family dashboard + shared care plans

### Day 20: Agent 9 — Pharmacy & Agent 10 — Voice Care
- **Pharmacy:** E-prescription → dispensing → adherence loop
- **Voice Care:** IVR + WhatsApp voice notes → STT (Whisper) → intake agent
- Both agents emit FHIR events for audit trail
- **Deliverable:** Pharmacy network connect + voice intake demo

---

## Phase 3: Clinical-Grade Polish (Days 21–27)

### Day 21: E2E Clinical Workflows
- OPD visit: Intake → Vitals → Consult → Rx → Lab → Follow-up
- IPD admission → discharge summary → post-discharge follow-up
- ANC/PNC pathway (high-priority for India)
- Emergency triage → stabilization → referral
- **Deliverable:** 4 complete workflow videos + test scripts

### Day 22: Performance & Scale
- Load test: 100 concurrent clinics, 10k patients, 50k encounters/day
- DB indexing, query optimization (pg_stat_statements)
- Redis caching strategy (session, FHIR search, agent state)
- Horizontal scaling: orchestrator workers, API replicas
- **Deliverable:** k6 report, p95 <200ms API, <5s agent processing

### Day 23: Offline-First & Sync
- Service Worker + IndexedDB for React SPA
- Conflict resolution (last-write-wins + clinical merge rules)
- Background sync on reconnect
- **Deliverable:** Works on 2G / intermittent connectivity

### Day 24: Regionalization (India)
- Languages: Hindi, Tamil, Telugu, Kannada, Marathi, Bengali, Gujarati, Malayalam
- RTL support for Urdu (future)
- Date/number formats per locale
- ICD-10 + NAMASTE code mapping
- **Deliverable:** i18n complete, language switcher in UI

### Day 25: Analytics & Reporting
- Clinical quality measures (NQF-aligned): HbA1c control, BP control, cancer screening
- Operational: wait times, no-show rate, agent throughput
- ABDM compliance dashboard (consent %, ABHA linkage %)
- Export: CSV, PDF, FHIR Bundle
- **Deliverable:** Admin analytics portal

### Day 26: Disaster Recovery & Backup
- Automated PG dump → S3 (encrypted) daily + WAL archiving
- RTO <1h, RPO <5min (streaming replication)
- Chaos engineering: kill primary, verify failover
- Runbook documentation
- **Deliverable:** DR drill passed, runbook published

### Day 27: Penetration Test & Compliance Sign-Off
- External pen test (OWASP ASVS Level 2)
- DPDP 2025 compliance audit (consent, rights, breach notification)
- ABDM sandbox certification
- SOC 2 Type II readiness (controls documented)
- **Deliverable:** Pen test report + compliance certificate

---

## Phase 4: Launch Preparation (Days 28–30)

### Day 28: Pilot Onboarding
- 3 pilot clinics (urban, semi-urban, rural)
- Data migration from existing EMR (CSV → FHIR)
- Staff training (WhatsApp-based microlearning)
- Support SLA: 4h response, 24h resolution
- **Deliverable:** 3 live clinics, feedback loop

### Day 29: Production Hardening
- Blue-green deploy to production VPC
- WAF rules, DDoS protection (Cloudflare)
- Monitoring: Prometheus + Grafana + Alertmanager (PagerDuty/Telegram)
- Log aggregation: Loki + structured JSON logs
- **Deliverable:** Prod deploy checklist 100% green

### Day 30: GA Release & Handoff
- Public launch: `healthplatform.in` + branded landing page
- Documentation: API docs (Redoc), admin guide, clinician guide
- Open-source community: Discord, GitHub Discussions, CONTRIBUTING.md
- Investor demo deck (traction: 3 clinics, X patients, Y encounters)
- **Deliverable:** v1.0.0 tag, launch announcement, handoff docs

---

## Success Criteria (Clinical-Ready Definition)

| Metric | Target |
|--------|--------|
| **Uptime** | ≥99.9% (excluding planned maintenance) |
| **API p95 latency** | <200ms |
| **FHIR validation** | 100% resources pass HL7 validator |
| **ABDM integration** | Sandbox certified, production-ready |
| **DPDP 2025** | Consent audit trail, rights APIs, breach notification <72h |
| **E2EE WhatsApp** | Zero PHI on non-E2EE channels |
| **Clinical workflows** | 4/4 pathways tested end-to-end |
| **Security** | Zero critical/high vulns, pen test passed |
| **Pilot adoption** | ≥80% clinician daily active use |
| **Data integrity** | Zero patient record loss in DR drill |

---

## Risk Register & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ABDM API changes | Medium | High | Adapter pattern, version pinning, sandbox monitoring |
| WhatsApp Business API policy shift | Low | Critical | Own Business App, fallback SMS/IVR, legal review |
| DPDP rules notification (draft→final) | Medium | High | Configurable consent engine, legal counsel retainer |
| Clinician adoption resistance | High | Medium | Co-design with pilot doctors, WhatsApp-native UX |
| Scale bottlenecks (PostgreSQL) | Medium | High | Read replicas, partitioning by `org_id`, caching layer |
| OCR accuracy (handwritten prescriptions) | High | Medium | Human-in-loop review, confidence thresholds, active learning |

---

## Resource Allocation (Solo Founder Mode)

| Week | Focus | Hours |
|------|-------|-------|
| 1 (Days 3–7) | Core compliance + ingestion | 60h |
| 2 (Days 8–14) | Multi-tenant + agents 1–3 | 60h |
| 3 (Days 15–21) | Agents 4–10 + workflows | 70h |
| 4 (Days 22–30) | Polish, pilot, launch | 70h |

**Tools:** Cursor + Antigravity IDE (MCP), Hermes kanban for task tracking, cloudflared for tunnels, GitHub Actions for CI.

---

## Daily Cadence

```
08:00  Social media cron (auto)
09:00  Standup (self) — review kanban, pick top 3
09:30  Deep work block 1
13:00  Lunch / walk
14:00  Deep work block 2
18:00  Commit + push + CI check
18:30  Update kanban, log blockers
19:00  Shutdown
```

**Weekend:** 4h Saturday (bug bash), Sunday off.

---

## Definition of Done per Day

- [ ] Code committed, CI green
- [ ] Kanban card moved to Done
- [ ] At least 1 E2E test added
- [ ] No critical security findings
- [ ] Docs updated (API / runbook)
- [ ] Pushed to GitHub (primary deliverable)

---

**Generated:** 2026-07-13  
**Repo:** github.com/19p1362/health-platform  
**Next:** Push this plan, start Day 3 (Auth/RBAC fix)