#!/usr/bin/env python3
"""
30-Day Clinical Build Plan - Loop System
Automated task management, progression tracking, and cron scheduling.
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

PROJECT_ROOT = Path("/mnt/c/AI agent Workflow/health-platform")

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"

class Phase(str, Enum):
    EXISTING = "Section B — Existing Strengths (Working Well)"
    FOUNDATION = "Foundation & Compliance (Days 1-10)"
    DOCTOR_WORKFLOW = "Doctor Workflow (Days 8-14)"
    FINANCIAL = "Financial (Days 15-21)"
    PATIENT_COMPLIANCE = "Patient + Compliance (Days 22-30)"

@dataclass
class Task:
    id: str
    day: int
    title: str
    description: str
    phase: Phase
    status: TaskStatus = TaskStatus.PENDING
    estimated_hours: float = 8.0
    dependencies: List[str] = None
    deliverables: List[str] = None
    completed_at: Optional[str] = None
    started_at: Optional[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.deliverables is None:
            self.deliverables = []

# ═══════════════════════════════════════════════════════════════
# 30-DAY TASK DEFINITION
# ═══════════════════════════════════════════════════════════════

TASKS: List[Task] = [
    # ═══════════════════════════════════════════════════════════════
    # Section B — What Already Exists & Works Well (COMPLETED)
    # ═══════════════════════════════════════════════════════════════
    Task("B.1", 0, "16 API Routers Fully Wired",
         "Auth, patients, FHIR R4, consent, compliance, admin, ingestion, conversion, exports, connectors, organizations, WhatsApp — all 16 routers fully implemented and registered",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["16 routers", "FastAPI integration", "OpenAPI docs"]),
    Task("B.2", 0, "DPDP 2025 Compliance Service (2,716 lines)",
         "Consent management, breach notification, erasure scheduling, cross-border transfer controls, grievance redressal (90-day SLA), data principal rights (access, correction, portability)",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["Consent engine", "Breach workflow", "Erasure scheduler", "Rights APIs", "90-day SLA"]),
    Task("B.3", 0, "FHIR Conversion Service (2,757 lines)",
         "C-CDA ↔ FHIR R4, HL7 v2 ↔ FHIR R4, FHIR ↔ PDF, structured and validated",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["C-CDA converter", "HL7 v2 converter", "PDF generator", "Validator"]),
    Task("B.4", 0, "Document Ingestion Pipeline",
         "Aadhaar eKYC, photo/PDF → OCR (Tesseract) → AI extraction → FHIR R4 Bundle with OTC verification, XML decryption, SHA-256 hashing",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["eKYC module", "OCR pipeline", "AI extraction", "FHIR Bundle output", "SHA-256 hashing"]),
    Task("B.5", 0, "ABHA Connector (595 lines)",
         "Ayushman Bharat Health Account — ABHA address linking, health record sharing, consent artefact management",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["ABHA linking", "Record sharing", "Consent artefacts"]),
    Task("B.6", 0, "Audit Trail (Append-Only, Context-Manager Pattern)",
         "Immutable audit logs, DPDP 1-year purge, context-manager for auto-capture, user/IP/action tracking",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["Append-only logs", "Auto-capture CM", "1-year purge", "Full traceability"]),
    Task("B.7", 0, "Fernet Encryption (3-Tier Key Resolution)",
         "Tier 1: Env var (FERNET_KEY), Tier 2: File (/etc/healthbridge/fernet.key), Tier 3: Auto-generated (dev), correct field masking in logs",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["3-tier resolution", "Field masking", "Key rotation ready"]),
    Task("B.8", 0, "Multi-Tenant Organizations",
         "Full org onboarding with slug, subscription tiers (FREE/STARTER/PROFESSIONAL/ENTERPRISE), staff limits, patient limits, 3 EHR connectors (ABDM, OpenMRS, Generic FHIR R4)",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["Org onboarding", "4 subscription tiers", "3 EHR connectors", "Staff/patient limits"]),
    Task("B.9", 0, "10 AI Care Agents (Orchestrator)",
         "All 10 agents execute end-to-end without exceptions (verified by --migrate --seed --orchestrator --once): Patient Intake, Medication Adherence, Follow-Up, Appointment, Risk Prediction, Family Care, Voice Care, Pharmacy, Lab, Insurance",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["10 agents", "Agent loop", "FHIR sync", "SQLite schema"]),
    Task("B.10", 0, "Frontend (14 Pages, 12 with Full State Handling)",
         "React 18 + TypeScript + Vite, polished dark theme (1,719-line CSS design system), TanStack Query (30s stale time, retry, no refetch on focus), Export Center (705 lines), Document Upload (drag-drop, preview, 6 doc types, patient search, recent uploads)",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["14 pages", "Design system", "TanStack Query", "Export Center", "Document Upload"]),
    Task("B.11", 0, "Orchestrator Strengths",
         "14-table SQLite schema with proper FKs, indexes, unique constraints (patients, meds, labs, appointments), real FHIR endpoint calls to backend (sync_from_healthbridge()), good code quality (type hints, docstrings, try/except on all DB/API calls)",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["14-table schema", "FHIR sync", "Type safety", "Error handling"]),
    Task("B.12", 0, "3 EHR Connectors",
         "ABDM (India), OpenMRS (open-source), Generic FHIR R4 — production-ready connectors with sync, test, and status endpoints",
         Phase.EXISTING, TaskStatus.COMPLETED, 0.0,
         deliverables=["ABDM connector", "OpenMRS connector", "Generic FHIR connector"]),

    # ═══════════════════════════════════════════════════════════════
    # Phase 1: Foundation & Compliance (Days 1-10)
    # ═══════════════════════════════════════════════════════════════
    Task("1.1", 1, "Fix datetime.utcnow() SQLAlchemy defaults", 
         "Replace all datetime.utcnow() defaults with utcnow() factory for per-row evaluation",
         Phase.FOUNDATION, TaskStatus.COMPLETED, 2.0, 
         deliverables=["utcnow() factory function", "17 model columns fixed"]),
    Task("1.2", 2, "Fix super admin org staff_count=0", 
         "Super admin org list now queries actual staff count per org",
         Phase.FOUNDATION, TaskStatus.COMPLETED, 1.0,
         deliverables=["Organizations API fixed"]),
    Task("1.3", 3, "OPD Registration + UHID + Token Queue",
         "Walk-in registration, UHID generation, token queue management",
         Phase.FOUNDATION, TaskStatus.COMPLETED, 16.0,
         deliverables=["OPDTokenQueue model", "UHID generator", "Token CRUD API", "Dashboard stats"]),
    Task("1.4", 4, "Vital Signs Entry (BP/Pulse/SpO₂/Temp/RBS)",
         "Nursing workflow for vital signs entry stored as FHIR Observations",
         Phase.FOUNDATION, TaskStatus.PENDING, 16.0,
         dependencies=["1.3"],
         deliverables=["Vitals API", "FHIR Observation profiles", "Nursing UI"]),
    Task("1.5", 5, "SOAP Clinical Notes Editor",
         "Structured Subjective/Objective/Assessment/Plan editor with templates",
         Phase.FOUNDATION, TaskStatus.PENDING, 16.0,
         dependencies=["1.4"],
         deliverables=["SOAP API", "Template system", "Rich text editor"]),
    Task("1.6", 6, "DPDP 2025 Consent Engine Hardening",
         "Consent artefacts, withdrawal flow, data principal rights APIs",
         Phase.FOUNDATION, TaskStatus.PENDING, 12.0,
         dependencies=["1.3"],
         deliverables=["Consent API", "Withdrawal flow", "Rights endpoints"]),
    Task("1.7", 7, "ABDM Integration Core",
         "ABHA verification, HFR/HPR sync, Scan & Share QR",
         Phase.FOUNDATION, TaskStatus.PENDING, 16.0,
         dependencies=["1.3"],
         deliverables=["ABDM API", "QR generation", "HFR/HPR sync"]),
    Task("1.8", 8, "FHIR R4 Resource Completeness",
         "Implement missing profiles: Patient, Observation, Condition, MedicationRequest, Encounter, DiagnosticReport, Immunization, ServiceRequest",
         Phase.FOUNDATION, TaskStatus.PENDING, 20.0,
         dependencies=["1.4"],
         deliverables=["All FHIR profiles", "Search params", "Bundle transactions"]),
    Task("1.9", 9, "Multi-Tenant SaaS Foundation",
         "Org isolation, subscription tiers, feature flags, usage metering",
         Phase.FOUNDATION, TaskStatus.PENDING, 16.0,
         dependencies=["1.3"],
         deliverables=["Org middleware", "Tier enforcement", "Usage API"]),
    Task("1.10", 10, "Testing & CI/CD Pipeline",
         "Unit/integration/contract tests, GitHub Actions, staging deploy",
         Phase.FOUNDATION, TaskStatus.PENDING, 12.0,
         dependencies=["1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"],
         deliverables=["Test suite", "CI pipeline", "Staging env"]),

    # Phase 2: Doctor Workflow (Days 8-14)
    Task("2.1", 8, "Prescription Writer (Drug Formulary + Structured Rx)",
         "Searchable drug database, dosage calculator, interaction checker",
         Phase.DOCTOR_WORKFLOW, TaskStatus.PENDING, 24.0,
         dependencies=["1.3", "1.5"],
         deliverables=["Drug formulary API", "Rx writer UI", "Interaction checker"]),
    Task("2.2", 9, "Lab Order + Results Entry",
         "Order tests, enter results with reference ranges, flag abnormals",
         Phase.DOCTOR_WORKFLOW, TaskStatus.PENDING, 16.0,
         dependencies=["2.1"],
         deliverables=["Lab order API", "Results entry", "Abnormal flagging"]),
    Task("2.3", 10, "Appointment Scheduler (Slot Calendar)",
         "Calendar view, phone booking, slot management, reminders",
         Phase.DOCTOR_WORKFLOW, TaskStatus.PENDING, 16.0,
         dependencies=["1.3"],
         deliverables=["Appointment API", "Calendar UI", "Reminder system"]),
    Task("2.4", 11, "Medication Adherence Tracking",
         "Dose schedule, reminders, missed dose alerts, pharmacy refill sync",
         Phase.DOCTOR_WORKFLOW, TaskStatus.PENDING, 16.0,
         dependencies=["2.1"],
         deliverables=["Adherence API", "Reminder engine", "Pharmacy sync"]),
    Task("2.5", 12, "Follow-Up Engine",
         "Rule-based triggers, escalation ladder, chronic care protocols",
         Phase.DOCTOR_WORKFLOW, TaskStatus.PENDING, 12.0,
         dependencies=["1.5", "2.3"],
         deliverables=["Follow-up rules", "Escalation API", "Protocol templates"]),
    Task("2.6", 13, "Risk Prediction Engine",
         "Rule engine + ML for sepsis, AKI, readmission, chronic progression",
         Phase.DOCTOR_WORKFLOW, TaskStatus.PENDING, 20.0,
         dependencies=["1.4", "2.2"],
         deliverables=["Risk API", "ML models", "SHAP explanations"]),
    Task("2.7", 14, "Family Care Coordinator",
         "Household linking, shared care plans, caregiver notifications",
         Phase.DOCTOR_WORKFLOW, TaskStatus.PENDING, 12.0,
         dependencies=["1.3", "1.6"],
         deliverables=["Family API", "Care plan sharing", "Caregiver UI"]),

    # Phase 3: Financial (Days 15-21)
    Task("3.1", 15, "Pharmacy Inventory (Batch/Expiry/Stock Alerts)",
         "Stock management, batch tracking, expiry alerts, dispense→inventory",
         Phase.FINANCIAL, TaskStatus.PENDING, 16.0,
         dependencies=["1.3", "2.1"],
         deliverables=["Inventory API", "Batch tracking", "Stock alerts"]),
    Task("3.2", 16, "Billing Engine (Invoice/GST/UPI/Card/Cash)",
         "Invoice generation, GST calculation, multi-payment, receipts",
         Phase.FINANCIAL, TaskStatus.PENDING, 20.0,
         dependencies=["1.3", "1.9"],
         deliverables=["Billing API", "GST engine", "Payment gateway"]),
    Task("3.3", 17, "IPD Admission + Bed Management",
         "Bed assignment, admission formalities, transfer/discharge workflow",
         Phase.FINANCIAL, TaskStatus.PENDING, 16.0,
         dependencies=["1.3", "3.2"],
         deliverables=["IPD API", "Bed management", "Admission workflow"]),
    Task("3.4", 18, "Discharge Summary (Structured Template + PDF)",
         "FHIR Composition, PDF generation, medication reconciliation",
         Phase.FINANCIAL, TaskStatus.PENDING, 12.0,
         dependencies=["3.3"],
         deliverables=["Discharge API", "PDF generator", "Med reconciliation"]),
    Task("3.5", 19, "Insurance/TPA Pre-Auth",
         "ABDM Claim bundle, pre-auth workflow, denial management",
         Phase.FINANCIAL, TaskStatus.PENDING, 20.0,
         dependencies=["3.2", "1.7"],
         deliverables=["Insurance API", "Pre-auth workflow", "Denial management"]),
    Task("3.6", 20, "Government Schemes (Aarogyasri/CGHS/ECHS)",
         "Scheme eligibility, rate cards, claim submission",
         Phase.FINANCIAL, TaskStatus.PENDING, 12.0,
         dependencies=["3.5"],
         deliverables=["Scheme API", "Rate card engine", "Eligibility checker"]),
    Task("3.7", 21, "NABH Clinical Audit + CGHS/ECHS Rate Cards",
         "Random case review workflow, audit trails, rate card management",
         Phase.FINANCIAL, TaskStatus.PENDING, 12.0,
         dependencies=["3.6"],
         deliverables=["Audit workflow", "Rate card API", "Review dashboard"]),

    # Phase 4: Patient + Compliance (Days 22-30)
    Task("4.1", 22, "Patient Portal (Login/View Records/Download Reports)",
         "Patient-facing portal with record access, consent management",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 20.0,
         dependencies=["1.3", "1.6", "1.9"],
         deliverables=["Portal UI", "Record access API", "Consent management"]),
    Task("4.2", 23, "Multi-Language (Telugu First, then Hindi)",
         "react-i18next integration, Telugu/Hindi translations, RTL ready",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 16.0,
         dependencies=["4.1"],
         deliverables=["i18n framework", "Telugu translations", "Hindi translations"]),
    Task("4.3", 24, "ABDM Scan & Share QR at Reception",
         "QR generation, patient consent, record sharing via ABDM",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 12.0,
         dependencies=["1.7", "4.1"],
         deliverables=["QR endpoint", "Consent flow", "Record sharing"]),
    Task("4.4", 25, "Orchestrator Dashboard UI + Real Message Delivery",
         "Flask dashboard with agent status, real SMS/WhatsApp/email delivery",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 16.0,
         dependencies=["1.3", "1.6"],
         deliverables=["Dashboard UI", "Message delivery", "Agent monitoring"]),
    Task("4.5", 26, "Offline-First PWA + Service Worker",
         "IndexedDB sync, conflict resolution, background sync",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 16.0,
         dependencies=["4.1", "4.2"],
         deliverables=["PWA manifest", "Service worker", "Sync engine"]),
    Task("4.6", 27, "LIS Integration (Erba/Roche/Siemens)",
         "Auto-import from lab machines, HL7/ASTML parsing",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 20.0,
         dependencies=["2.2", "3.1"],
         deliverables=["LIS connectors", "Auto-import", "Result mapping"]),
    Task("4.7", 28, "Docker Containers + Production Deployment",
         "All services containerized, docker-compose, Kubernetes ready",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 8.0,
         dependencies=["1.10", "4.1", "4.3", "4.4"],
         deliverables=["Dockerfiles", "docker-compose", "K8s manifests"]),
    Task("4.8", 29, "E-Prescription (ABDM Push) + OT/Surgery Scheduling",
         "Push Rx to ABDM, theatre booking, pre-op checklist",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 12.0,
         dependencies=["2.1", "1.7", "3.3"],
         deliverables=["ABDM Rx push", "OT scheduler", "Pre-op checklist"]),
    Task("4.9", 30, "End-to-End Integration Test + Production .env + Docker",
         "Full system test, production config, launch checklist",
         Phase.PATIENT_COMPLIANCE, TaskStatus.PENDING, 16.0,
         dependencies=["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9"],
         deliverables=["E2E test suite", "Production config", "Launch checklist"]),
]

# ═══════════════════════════════════════════════════════════════
# Loop System
# ═══════════════════════════════════════════════════════════════

class LoopSystem:
    def __init__(self):
        self.tasks = {t.id: t for t in TASKS}
        self.state_file = PROJECT_ROOT / "loop_state.json"
        self.load_state()
    
    def load_state(self):
        """Load persisted state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                for task_id, task_data in data.get("tasks", {}).items():
                    if task_id in self.tasks:
                        self.tasks[task_id].status = TaskStatus(task_data.get("status", "PENDING"))
                        self.tasks[task_id].completed_at = task_data.get("completed_at")
                        self.tasks[task_id].started_at = task_data.get("started_at")
            except Exception:
                pass
    
    def save_state(self):
        """Persist state to file."""
        data = {
            "tasks": {
                task_id: {
                    "status": task.status.value,
                    "completed_at": task.completed_at,
                    "started_at": task.started_at,
                }
                for task_id, task in self.tasks.items()
            },
            "last_updated": datetime.now().isoformat(),
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)
    
    def start_task(self, task_id: str) -> bool:
        """Start a task if dependencies are met."""
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        # Check dependencies
        for dep_id in task.dependencies:
            dep = self.tasks.get(dep_id)
            if dep and dep.status != TaskStatus.COMPLETED:
                print(f"  ⚠️ Dependency {dep_id} not completed")
                return False
        
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        self.save_state()
        return True
    
    def complete_task(self, task_id: str) -> bool:
        """Mark task as completed."""
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self.save_state()
        return True
    
    def get_next_actionable_task(self) -> Optional[Task]:
        """Get the next task that can be started (dependencies met, not started)."""
        # Sort by day, then by task id
        sorted_tasks = sorted(self.tasks.values(), key=lambda t: (int(t.id.split('.')[0]), t.id))
        
        for task in sorted_tasks:
            if task.status == TaskStatus.PENDING:
                # Check dependencies
                deps_met = all(
                    self.tasks[dep].status == TaskStatus.COMPLETED 
                    for dep in task.dependencies 
                    if dep in self.tasks
                )
                if deps_met:
                    return task
        return None
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get progress summary by phase."""
        summary = {}
        for phase in Phase:
            phase_tasks = [t for t in self.tasks.values() if t.phase == phase]
            completed = sum(1 for t in phase_tasks if t.status == TaskStatus.COMPLETED)
            in_progress = sum(1 for t in phase_tasks if t.status == TaskStatus.IN_PROGRESS)
            pending = sum(1 for t in phase_tasks if t.status == TaskStatus.PENDING)
            total = len(phase_tasks)
            
            summary[phase.value] = {
                "total": total,
                "completed": completed,
                "in_progress": in_progress,
                "pending": pending,
                "progress_pct": round((completed / total * 100) if total > 0 else 0, 1),
            }
        return summary
    
    def generate_report(self) -> str:
        """Generate formatted progress report."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = f"📋 **30-DAY BUILD LOOP REPORT**\n"
        report += f"⏰ {now}\n\n"
        
        summary = self.get_progress_summary()
        total_completed = sum(s["completed"] for s in summary.values())
        total_tasks = sum(s["total"] for s in summary.values())
        
        report += f"📊 **Overall**: {total_completed}/{total_tasks} tasks completed ({round(total_completed/total_tasks*100, 1)}%)\n\n"
        
        for phase_name, stats in summary.items():
            report += f"**{phase_name}**\n"
            report += f"  ✅ {stats['completed']}  🔄 {stats['in_progress']}  ⏳ {stats['pending']}  ({stats['progress_pct']}%)\n"
            
            # Show next actionable task in this phase
            phase_tasks = [t for t in self.tasks.values() if t.phase.value == phase_name]
            next_task = next((t for t in phase_tasks if t.status == TaskStatus.PENDING), None)
            if next_task:
                deps_met = all(
                    self.tasks[dep].status == TaskStatus.COMPLETED 
                    for dep in next_task.dependencies 
                    if dep in self.tasks
                )
                status = "🟢 Ready" if deps_met else "🔴 Blocked"
                report += f"  → Next: {next_task.id} - {next_task.title} ({status})\n"
            report += "\n"
        
        # Show currently in-progress tasks
        in_progress = [t for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS]
        if in_progress:
            report += "**🔄 Currently In Progress:**\n"
            for task in in_progress:
                report += f"  • {task.id} - {task.title}\n"
            report += "\n"
        
        report += "---\n*Auto-generated by 30-Day Build Loop System*"
        return report
    
    async def send_report_via_mcp(self):
        """Send report via Hermes MCP to Telegram."""
        report = self.generate_report()
        
        init_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "30day-loop", "version": "1.0"}
            }
        }
        
        send_msg = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "messages_send",
                "arguments": {
                    "target": "telegram:6112495820",
                    "message": report
                }
            }
        }
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "/home/abisa/.local/bin/hermes", "mcp", "serve", "--accept-hooks",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            input_data = json.dumps(init_msg) + "\n" + \
                        json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"}) + "\n" + \
                        json.dumps(send_msg) + "\n"
            
            await asyncio.wait_for(proc.communicate(input=input_data.encode()), timeout=15)
            return True
        except Exception as e:
            print(f"MCP send error: {e}")
            return False


# ═══════════════════════════════════════════════════════════════
# CLI Commands
# ═══════════════════════════════════════════════════════════════

def cmd_status():
    loop = LoopSystem()
    print(loop.generate_report())

def cmd_next():
    loop = LoopSystem()
    task = loop.get_next_actionable_task()
    if task:
        print(f"Next actionable task: {task.id} - {task.title}")
        print(f"  Day: {task.day}, Phase: {task.phase.value}")
        print(f"  Estimated: {task.estimated_hours}h")
        print(f"  Dependencies: {', '.join(task.dependencies) if task.dependencies else 'None'}")
        print(f"  Deliverables: {', '.join(task.deliverables)}")
    else:
        print("No actionable tasks available")

def cmd_start(task_id: str):
    loop = LoopSystem()
    if loop.start_task(task_id):
        task = loop.get_task(task_id)
        print(f"✅ Started: {task.id} - {task.title}")
    else:
        print(f"❌ Cannot start {task_id} - dependencies not met or invalid ID")

def cmd_complete(task_id: str):
    loop = LoopSystem()
    if loop.complete_task(task_id):
        print(f"✅ Completed: {task_id}")
    else:
        print(f"❌ Task {task_id} not found")

def cmd_report():
    loop = LoopSystem()
    print(loop.generate_report())

async def cmd_send_report():
    loop = LoopSystem()
    if await loop.send_report_via_mcp():
        print("✅ Report sent via Telegram")
    else:
        print("❌ Failed to send report")

def cmd_list():
    loop = LoopSystem()
    def sort_key(t):
        try:
            return (int(t.id.split('.')[0]), t.id)
        except ValueError:
            return (999, t.id)  # Put non-numeric IDs at the end
    for task in sorted(loop.tasks.values(), key=sort_key):
        status_icon = {
            TaskStatus.COMPLETED: "✅",
            TaskStatus.IN_PROGRESS: "🔄",
            TaskStatus.PENDING: "⏳",
            TaskStatus.BLOCKED: "🚫",
            TaskStatus.SKIPPED: "⏭️",
        }.get(task.status, "❓")
        
        deps = f" [{', '.join(task.dependencies)}]" if task.dependencies else ""
        print(f"  {status_icon} {task.id} - {task.title} (Day {task.day}){deps}")


# ═══════════════════════════════════════════════════════════════
# Cron Integration
# ═══════════════════════════════════════════════════════════════

def setup_cron_jobs():
    """Set up cron jobs for the loop system."""
    cron_entries = [
        # Daily progress report at 9 AM
        "0 9 * * * cd /mnt/c/AI\\ agent\\ Workflow/health-platform && python3 loop_system.py report",
        
        # Auto-advance check every 4 hours
        "0 */4 * * * cd /mnt/c/AI\\ agent\\ Workflow/health-platform && python3 loop_system.py next >> /tmp/loop_next.log 2>&1",
        
        # Weekly summary on Monday 8 AM
        "0 8 * * 1 cd /mnt/c/AI\\ agent\\ Workflow/health-platform && python3 loop_system.py send-report",
    ]
    
    print("Add these to crontab (crontab -e):")
    for entry in cron_entries:
        print(f"  {entry}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python loop_system.py [status|next|start|complete|report|send-report|list|setup-cron] [task_id]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        cmd_status()
    elif cmd == "next":
        cmd_next()
    elif cmd == "start" and len(sys.argv) > 2:
        cmd_start(sys.argv[2])
    elif cmd == "complete" and len(sys.argv) > 2:
        cmd_complete(sys.argv[2])
    elif cmd == "report":
        cmd_report()
    elif cmd == "send-report":
        asyncio.run(cmd_send_report())
    elif cmd == "list":
        cmd_list()
    elif cmd == "setup-cron":
        setup_cron_jobs()
    else:
        print(f"Unknown command: {cmd}")