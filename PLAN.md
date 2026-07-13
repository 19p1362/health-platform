# Health-Platform: 30-Day Clinical-Ready Build Plan (from photo)

**Source:** Handwritten plan photo (2026-06-29)  
**Stack:** FastAPI + React + Orchestrator — builds on existing auth, FHIR, compliance, audit, ingestion, export, connectors  
**Note:** *"All this builds on top of what already works — you're not rewriting, you're adding the clinical layer."*

---

## Week 1: Core Clinical (Days 1–7)

| Day | Task |
|-----|------|
| 1–2 | Fix all 18 CRITICAL/HIGH bugs |
| 3–4 | OPD Registration + UHID + Token Queue |
| 5–6 | Vital Signs Entry (BP / Pulse / SpO₂ / Temp / RBS) |
| 7 | SOAP Clinical Notes Editor |

---

## Week 2: Doctor Workflow (Days 8–14)

| Day | Task |
|-----|------|
| 8–10 | Prescription Writer (drug formulary, structured Rx) |
| 11–12 | Lab Order + Results Entry |
| 13–14 | Appointment Scheduler (slot calendar) |

---

## Week 3: Financial (Days 15–21)

| Day | Task |
|-----|------|
| 15–16 | Pharmacy Inventory (batch, expiry, stock alerts) |
| 17–18 | Billing Engine (invoice, GST, cash/UPI/card) |
| 19–20 | IPD Admission + Bed Management |
| 21 | Discharge Summary (structured template + PDF) |

---

## Week 4: Patient + Compliance (Days 22–30)

| Day | Task |
|-----|------|
| 22–23 | Patient Portal (login, view records, download reports) |
| 24–25 | Multi-Language (react-i18next — Telugu first, then Hindi) |
| 26–27 | ABDM Scan & Share QR at reception |
| 28–29 | Orchestrator Dashboard UI + real message delivery |
| 30 | End-to-end integration test + production .env + Docker |

---

## Real Hospital Flow (from plan)

> **F. HOW IT WORKS PROPERLY IN A HOSPITAL (The Real Flow)**  
> A doctor or nurse would use HealthBridge in a real clinic. A patient would need this 5-minute workflow.

---

## Status Context

- **Days 1–2 (Bug Fixes):** ✅ Done — commit `9d83872` "fix: resolve all 10 CRITICAL/HIGH bugs from Day 1-2 audit"
- **Current:** Ready to start Day 3 (OPD Registration + UHID + Token Queue)
- **Existing foundation:** auth, FHIR, compliance, audit, ingestion, export, connectors — all working

---

**Extracted:** 2026-07-13 via vision analysis  
**Photo date:** 2026-06-29  
**Repo:** github.com/19p1362/health-platform