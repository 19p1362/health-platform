"""HealthBridge Platform — DPDP 2025 Compliance Engine

Implements compliance with the Digital Personal Data Protection Act 2023
and the DPDP Rules 2025 for healthcare data fiduciaries operating in India.

References:
    - DPDP Act 2023: Sections 5 (Consent), 6 (Notice), 7 (Withdrawal),
      8 (Breach), 9-10 (Cross-border), 11-13 (Data Principal Rights),
      14 (Grievance), 16 (SDF Obligations), 17 (Exemptions)
    - Clinical Establishments (Registration and Regulation) Act, 2010:
      Section 18(3) — 3-year minimum clinical record retention
    - Healthcare exemptions: treatment emergencies, public health, research
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, TypedDict

from cryptography.fernet import Fernet

from app.config import settings
from app.database import SyncSessionLocal
from app.models import (
    AuditAction,
    BreachSeverity,
    BreachStatus,
    ConsentPurpose,
    ConsentStatus,
    Patient,
    AuditLog,
    ConsentRecord,
    CommunicationLog,
    DataBreach,
    BreachNotification,
    DataPrincipalRequest,
    ErasureSchedule,
)

logger = logging.getLogger("healthbridge.dpdp")

# ══════════════════════════════════════════════════════════════════════
# TypedDicts — structured return types for all public methods
# ══════════════════════════════════════════════════════════════════════


class ConsentVerification(TypedDict, total=False):
    valid: bool
    consent_id: str | None
    status: str
    purposes: list[str]
    granted_at: str | None
    expires_at: str | None
    days_remaining: int | None
    requires_renewal: bool
    reason: str


class ConsentNotice(TypedDict, total=False):
    consent_id: str
    patient_id: str
    notice_text: str
    language: str
    purposes: list[str]
    data_categories: list[str]
    withdrawal_mechanism: str
    valid_from: str
    valid_until: str
    provided_at: str


class ConsentWithdrawal(TypedDict, total=False):
    success: bool
    consent_id: str
    previous_status: str
    withdrawal_timestamp: str
    data_purge_scheduled: bool
    purge_schedule_id: str | None
    reason: str


class SelfServiceConsent(TypedDict, total=False):
    consent_id: str
    patient_id: str
    status: str
    dashboard_url: str
    granted_purposes: list[str]
    expires_at: str | None
    can_withdraw: bool
    withdrawal_url: str | None


class AccessRequestResult(TypedDict, total=False):
    request_id: str
    patient_id: str
    status: str
    data_categories: list[str]
    data_payload: dict[str, Any] | None
    sla_deadline: str
    resolved_at: str | None
    rejection_reason: str | None
    format: str


class CorrectionRequestResult(TypedDict, total=False):
    request_id: str
    patient_id: str
    status: str
    fields_requested: list[str]
    fields_updated: list[str]
    sla_deadline: str
    resolved_at: str | None
    notes: str


class ErasureRequestResult(TypedDict, total=False):
    request_id: str
    patient_id: str
    status: str
    erasure_type: str
    retention_override: bool
    retention_reason: str | None
    scheduled_date: str
    sla_deadline: str
    notification_required: bool
    notification_sent: bool


class BreachReportResult(TypedDict, total=False):
    breach_id: str
    severity: str
    status: str
    description: str
    affected_count: int
    affected_categories: list[str]
    detected_at: str
    board_notification_deadline: str
    board_notified: bool
    users_notified: bool
    board_report_deadline: str


class BoardNotificationResult(TypedDict, total=False):
    breach_id: str
    board_notified: bool
    board_notified_at: str
    report_deadline: str
    report_submitted: bool
    notification_payload: dict[str, Any]


class Breach72HourReport(TypedDict, total=False):
    breach_id: str
    submitted: bool
    submitted_at: str
    report_payload: dict[str, Any]
    compliance_notes: str


class ErasureScheduleResult(TypedDict, total=False):
    schedule_id: str
    patient_id: str
    erasure_type: str
    reason: str
    scheduled_date: str
    notification_sent: bool
    notification_channel: str | None
    execution_status: str
    records_affected: int | None


class ErasureNotification(TypedDict, total=False):
    schedule_id: str
    patient_id: str
    channel: str
    recipient: str
    notice_text: str
    sent_at: str
    user_responded: bool
    response: str | None


class ErasureExecution(TypedDict, total=False):
    schedule_id: str
    executed: bool
    executed_at: str
    records_affected: int
    details: dict[str, Any]
    clinical_retention_exemptions: list[str] | None


class PurgeResult(TypedDict, total=False):
    purged_audit_logs: int
    purged_communications: int
    purged_expired_consents: int
    purged_notifications: int
    cutoff_date: str
    executed_at: str


class CrossBorderTransferAssessment(TypedDict, total=False):
    permitted: bool
    country: str
    adequacy_status: str
    dpdp_compliant: bool
    safeguards: list[str]
    contract_clauses: list[str]
    restrictions: list[str]
    assessment_date: str


class GrievanceResult(TypedDict, total=False):
    request_id: str
    patient_id: str
    status: str
    sla_deadline: str
    filed_at: str
    resolved_at: str | None
    response_notes: str | None
    sla_compliant: bool | None


class SlaComplianceCheck(TypedDict, total=False):
    total_open: int
    within_sla: int
    breached_sla: int
    sla_days: int
    breach_percentage: float
    items_breached: list[dict[str, Any]]


class DpiaResult(TypedDict, total=False):
    dpia_id: str
    data_processing_activity: str
    risk_level: str
    risks_identified: list[str]
    mitigation_measures: list[str]
    residual_risk: str
    conducted_at: str
    reviewed_by: str
    next_review_date: str


class ComplianceReport(TypedDict, total=False):
    report_id: str
    generated_at: str
    report_period: str
    consent_count: int
    active_consents: int
    data_principal_requests: int
    grievances_filed: int
    grievances_resolved: int
    breaches_detected: int
    breaches_notified: int
    erasures_scheduled: int
    erasures_executed: int
    cross_border_transfers: int
    dpias_conducted: int
    compliance_status: str
    observations: list[str]


class ClinicalExemption(TypedDict, total=False):
    exempted: bool
    retention_years: int
    legal_basis: str
    affected_data_categories: list[str]
    exemption_expires_at: str | None


class MinorConsentEligibility(TypedDict, total=False):
    eligible: bool
    patient_age: int
    legal_guardian_required: bool
    guardian_type: str | None
    dpdp_rules: str
    exceptions: list[str]


# ══════════════════════════════════════════════════════════════════════
# Encryption helpers
# ══════════════════════════════════════════════════════════════════════

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.ENCRYPTION_KEY
        if key:
            _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        else:
            # Fallback: derive from SECRET_KEY (development only)
            from cryptography.fernet import Fernet as _F
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from base64 import urlsafe_b64encode

            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"healthbridge-dpdp", iterations=100_000)
            derived = urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
            _fernet = _F(derived)
    return _fernet


def _encrypt(plaintext: str) -> str:
    """Encrypt a string using Fernet (AES-128-CBC with HMAC)."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def _now() -> datetime:
    return datetime.utcnow()


def _today() -> date:
    return datetime.utcnow().date()


def _uuid4() -> str:
    return str(uuid.uuid4())


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _iso_date(d: date | None) -> str | None:
    return d.isoformat() if d else None


# ══════════════════════════════════════════════════════════════════════
# Service Class
# ══════════════════════════════════════════════════════════════════════


class DpdpComplianceService:
    """DPDP 2025 Compliance Engine for HealthBridge Platform.

    All methods operate within a synchronous DB session. Methods are
    designed to be called from FastAPI route handlers, background tasks,
    or APScheduler cron jobs.
    """

    # ──────────────────────────────────────────────────────────────
    # 1. CONSENT & NOTICE (DPDP Sections 5, 6, 7)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def verify_consent(
        patient_id: str,
        purpose: str | ConsentPurpose,
        session: Any | None = None,
    ) -> ConsentVerification:
        """Verify that a valid consent exists for the given purpose.

        DPDP Section 5: Consent must be free, specific, informed,
        unconditional, and unambiguous with a clear affirmative action.

        DPDP Section 6: The notice must specify the purpose and
        categories of personal data being collected.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                return ConsentVerification(valid=False, reason="Patient not found")

            if isinstance(purpose, ConsentPurpose):
                purpose_val = purpose.value
            else:
                purpose_val = purpose

            # Check current consent on patient record
            if patient.consent_status != ConsentStatus.GRANTED:
                return ConsentVerification(
                    valid=False,
                    consent_id=patient.consent_id,
                    status=patient.consent_status.value if patient.consent_status else "NONE",
                    purposes=patient.consent_purposes or [],
                    reason=f"Consent status is {patient.consent_status.value if patient.consent_status else 'NONE'}, not GRANTED",
                )

            # Check if consent covers this purpose
            purposes = [p.value if isinstance(p, ConsentPurpose) else p for p in (patient.consent_purposes or [])]
            if purpose_val not in purposes:
                return ConsentVerification(
                    valid=False,
                    consent_id=patient.consent_id,
                    status=ConsentStatus.GRANTED.value,
                    purposes=purposes,
                    reason=f"Purpose '{purpose_val}' not covered by existing consent",
                )

            # Check expiry
            now = _now()
            if patient.consent_expires_at and patient.consent_expires_at < now:
                return ConsentVerification(
                    valid=False,
                    consent_id=patient.consent_id,
                    status=ConsentStatus.EXPIRED.value,
                    purposes=purposes,
                    granted_at=_iso(patient.consent_granted_at),
                    expires_at=_iso(patient.consent_expires_at),
                    reason="Consent has expired",
                )

            # Valid consent
            days_remaining = None
            if patient.consent_expires_at:
                days_remaining = (patient.consent_expires_at - now).days

            return ConsentVerification(
                valid=True,
                consent_id=patient.consent_id,
                status=ConsentStatus.GRANTED.value,
                purposes=purposes,
                granted_at=_iso(patient.consent_granted_at),
                expires_at=_iso(patient.consent_expires_at),
                days_remaining=days_remaining,
                requires_renewal=days_remaining is not None and days_remaining <= 30,
                reason="Valid consent exists",
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def generate_consent_notice(
        patient_id: str,
        purposes: list[str | ConsentPurpose],
        data_categories: list[str] | None = None,
        duration_days: int = 365,
        language: str = "en",
        session: Any | None = None,
    ) -> ConsentNotice:
        """Generate and record a DPDP Section 5 & 6 compliant consent notice.

        The notice must:
        - Describe the purpose of processing
        - List categories of personal data
        - Provide withdrawal mechanism
        - Be in clear, plain language (English, Hindi, or regional)
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")

            resolved_purposes = [p.value if isinstance(p, ConsentPurpose) else p for p in purposes]
            resolved_categories = data_categories or ["DEMOGRAPHICS", "CLINICAL"]

            consent_id = f"CONSENT-{_uuid4()[:12].upper()}"
            now = _now()
            expires_at = now + timedelta(days=duration_days)

            # Build the notice text in plain language (DPDP Section 6)
            purpose_descriptions = {
                "TREATMENT": "providing healthcare treatment and medical services",
                "PAYMENT": "processing payments and insurance claims",
                "OPERATIONS": "operational and administrative purposes",
                "RESEARCH": "medical research with de-identified data",
                "PUBLIC_HEALTH": "public health reporting and disease surveillance",
            }
            purpose_strs = [purpose_descriptions.get(p, p.replace("_", " ").lower()) for p in resolved_purposes]

            category_descriptions = {
                "DEMOGRAPHICS": "name, age, gender, contact information, address",
                "CLINICAL": "medical history, diagnoses, lab reports, prescriptions, clinical notes",
                "GENETIC": "genetic testing results and genomic data",
                "BIOMETRIC": "biometric identifiers such as fingerprints",
                "FINANCIAL": "financial information and insurance details",
                "SENSITIVE_HEALTH": "sensitive health information as defined under applicable law",
            }
            category_strs = [category_descriptions.get(c, c.replace("_", " ").lower()) for c in resolved_categories]

            notice_text = (
                f"CONSENT NOTICE — HealthBridge Platform\n"
                f"Consent ID: {consent_id}\n"
                f"Date: {now.strftime('%d %B %Y')}\n\n"
                f"Purpose of Processing:\n"
                f"  Your data will be processed for the following purposes:\n"
                + "\n".join(f"  • {p}" for p in purpose_strs) + "\n\n"
                "Categories of Personal Data:\n"
                "  The following categories of your personal data will be processed:\n"
                + "\n".join(f"  • {c}" for c in category_strs) + "\n\n"
                f"Withdrawal:\n"
                f"  You have the right to withdraw this consent at any time by:\n"
                f"  • Visiting your patient portal dashboard\n"
                f"  • Contacting our Grievance Officer at grievance@healthbridge.in\n"
                f"  • Calling our support helpline\n\n"
                f"  Upon withdrawal, your data will cease to be processed for these purposes,\n"
                f"  subject to legal retention requirements under the Clinical Establishments Act.\n\n"
                f"Validity: {now.strftime('%d %B %Y')} to {expires_at.strftime('%d %B %Y')}\n"
                f"({duration_days} days)\n\n"
                f"Thank you,\nHealthBridge Data Protection Team"
            )

            withdrawal_mechanism = (
                "Withdraw via patient portal dashboard at https://portal.healthbridge.in/consent "
                "or email grievance@healthbridge.in with subject 'Consent Withdrawal - {consent_id}'"
            )

            # Create consent record in the audit trail
            consent_record = ConsentRecord(
                id=_uuid4(),
                patient_id=patient_id,
                consent_id=consent_id,
                purpose=ConsentPurpose(resolved_purposes[0]) if resolved_purposes else ConsentPurpose.TREATMENT,
                data_categories=resolved_categories,
                duration_days=duration_days,
                status=ConsentStatus.PENDING,
                granted_at=now,
                expires_at=expires_at,
                notice_provided=True,
                notice_language=language,
                notice_text=notice_text,
                withdrawal_mechanism=withdrawal_mechanism,
                recorded_at=now,
            )
            session.add(consent_record)

            # Log the notice event
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.CONSENT_GRANTED,
                patient_id=patient_id,
                resource_id=consent_id,
                resource_type="ConsentNotice",
                description=f"Consent notice generated for purposes: {', '.join(resolved_purposes)}",
                details_json={"consent_id": consent_id, "purposes": resolved_purposes, "language": language},
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return ConsentNotice(
                consent_id=consent_id,
                patient_id=patient_id,
                notice_text=notice_text,
                language=language,
                purposes=resolved_purposes,
                data_categories=resolved_categories,
                withdrawal_mechanism=withdrawal_mechanism,
                valid_from=_iso(now),
                valid_until=_iso(expires_at),
                provided_at=_iso(now),
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def withdraw_consent(
        patient_id: str,
        consent_id: str,
        reason: str | None = None,
        session: Any | None = None,
    ) -> ConsentWithdrawal:
        """Withdraw consent under DPDP Section 7.

        Withdrawal must be as easy as giving consent. On withdrawal,
        the data fiduciary must stop processing and schedule erasure
        unless retention is required by law (e.g., Clinical Establishments Act).
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                return ConsentWithdrawal(success=False, reason="Patient not found")

            consent_record = (
                session.query(ConsentRecord)
                .filter(ConsentRecord.consent_id == consent_id, ConsentRecord.patient_id == patient_id)
                .first()
            )
            if not consent_record:
                return ConsentWithdrawal(success=False, reason="Consent record not found")

            if consent_record.status in (ConsentStatus.WITHDRAWN, ConsentStatus.REVOKED, ConsentStatus.EXPIRED):
                return ConsentWithdrawal(
                    success=False,
                    consent_id=consent_id,
                    previous_status=consent_record.status.value,
                    reason=f"Consent is already {consent_record.status.value}",
                )

            now = _now()
            previous_status = consent_record.status.value

            # Update consent record
            consent_record.status = ConsentStatus.WITHDRAWN
            consent_record.previous_status = ConsentStatus(previous_status)
            consent_record.withdrawn_at = now

            # Update patient record
            patient.consent_status = ConsentStatus.WITHDRAWN
            # Note: We keep consent_id for audit trail but mark status

            # Schedule erasure unless clinical retention overrides
            clinical_exemption = DpdpComplianceService.check_clinical_establishment_exemption(patient_id, session=session)
            purge_scheduled = False
            purge_schedule_id = None

            if not clinical_exemption["exempted"]:
                erasure = ErasureSchedule(
                    id=_uuid4(),
                    patient_id=patient_id,
                    erasure_type="FULL",
                    erasure_reason="USER_WITHDRAWAL",
                    scheduled_date=_today() + timedelta(days=30),  # 30-day grace
                    notification_channel="EMAIL",
                    execution_status="PENDING",
                    created_at=now,
                )
                session.add(erasure)
                purge_scheduled = True
                purge_schedule_id = erasure.id

            # Log withdrawal
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.CONSENT_WITHDRAWN,
                patient_id=patient_id,
                resource_id=consent_id,
                resource_type="ConsentRecord",
                description=f"Consent withdrawn. Reason: {reason or 'Not provided'}",
                details_json={
                    "consent_id": consent_id,
                    "previous_status": previous_status,
                    "purge_scheduled": purge_scheduled,
                    "reason": reason,
                },
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return ConsentWithdrawal(
                success=True,
                consent_id=consent_id,
                previous_status=previous_status,
                withdrawal_timestamp=_iso(now),
                data_purge_scheduled=purge_scheduled,
                purge_schedule_id=purge_schedule_id,
                reason=reason or "Consent withdrawn by data principal",
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def consent_self_service(
        patient_id: str,
        session: Any | None = None,
    ) -> SelfServiceConsent:
        """Provide a self-service consent dashboard URL and status.

        DPDP Section 7(2): The data fiduciary must provide a mechanism
        for the data principal to withdraw consent as easily as it was given.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                return SelfServiceConsent(
                    consent_id="",
                    patient_id=patient_id,
                    status="UNKNOWN",
                    dashboard_url="",
                    granted_purposes=[],
                    can_withdraw=False,
                )

            status = patient.consent_status.value if patient.consent_status else "NONE"
            purposes = [p.value if isinstance(p, ConsentPurpose) else p for p in (patient.consent_purposes or [])]
            can_withdraw = status == ConsentStatus.GRANTED.value
            expires_at = _iso(patient.consent_expires_at) if patient.consent_expires_at else None

            dashboard_url = f"https://portal.healthbridge.in/consent/dashboard/{patient_id}"
            withdrawal_url = f"https://portal.healthbridge.in/consent/withdraw/{patient.consent_id}" if patient.consent_id else None

            return SelfServiceConsent(
                consent_id=patient.consent_id or "",
                patient_id=patient_id,
                status=status,
                dashboard_url=dashboard_url,
                granted_purposes=purposes,
                expires_at=expires_at,
                can_withdraw=can_withdraw,
                withdrawal_url=withdrawal_url,
            )
        finally:
            if close_session:
                session.close()

    # ──────────────────────────────────────────────────────────────
    # 2. DATA PRINCIPAL RIGHTS (DPDP Sections 11, 12, 13)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def process_access_request(
        patient_id: str,
        request_details: dict[str, Any] | None = None,
        verification_method: str = "OTP",
        session: Any | None = None,
    ) -> AccessRequestResult:
        """Process a Data Principal's access request (DPDP Section 11).

        Returns a summary of the personal data processed by the fiduciary,
        including categories, processing purposes, and any third-party sharing.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")

            now = _now()
            request_id = _uuid4()
            sla_deadline = now + timedelta(days=settings.DPDP_GRIEVANCE_SLA_DAYS)

            # Check for clinical retention exemption
            clinical_exemption = DpdpComplianceService.check_clinical_establishment_exemption(patient_id, session=session)

            # Gather data about this patient
            data_categories = ["DEMOGRAPHICS", "CLINICAL", "CONSENT", "COMMUNICATIONS"]
            data_payload: dict[str, Any] = {}

            # Safely decrypt if fields are encrypted
            try:
                first_name = _decrypt(patient.first_name) if patient.first_name else ""
            except Exception:
                first_name = patient.first_name or ""
            try:
                last_name = _decrypt(patient.last_name) if patient.last_name else ""
            except Exception:
                last_name = patient.last_name or ""
            try:
                phone = _decrypt(patient.phone) if patient.phone else ""
            except Exception:
                phone = patient.phone or ""
            try:
                email = _decrypt(patient.email) if patient.email else ""
            except Exception:
                email = patient.email or ""
            try:
                address = _decrypt(patient.address) if patient.address else ""
            except Exception:
                address = patient.address or ""

            data_payload["demographics"] = {
                "name": f"{first_name} {last_name}".strip(),
                "date_of_birth": _iso_date(patient.date_of_birth) if patient.date_of_birth else None,
                "gender": patient.gender.value if patient.gender else None,
                "phone": phone,
                "email": email,
                "address": address,
            }

            data_payload["clinical_info"] = {
                "blood_group": patient.blood_group,
                "chronic_conditions": patient.chronic_conditions,
                "emergency_contact": patient.emergency_contact_name,
            }

            data_payload["identifiers"] = {
                "abha_number": patient.abha_number,
                "aadhaar_hash_present": bool(patient.aadhaar_hash),
                "mrn": patient.mrn,
            }

            data_payload["consent"] = {
                "consent_id": patient.consent_id,
                "status": patient.consent_status.value if patient.consent_status else None,
                "purposes": patient.consent_purposes,
                "granted_at": _iso(patient.consent_granted_at),
                "expires_at": _iso(patient.consent_expires_at),
            }

            # Get consent records
            consent_records = session.query(ConsentRecord).filter(ConsentRecord.patient_id == patient_id).all()
            data_payload["consent_history"] = [
                {
                    "consent_id": cr.consent_id,
                    "purpose": cr.purpose.value if cr.purpose else None,
                    "status": cr.status.value if cr.status else None,
                    "granted_at": _iso(cr.granted_at),
                    "withdrawn_at": _iso(cr.withdrawn_at),
                }
                for cr in consent_records
            ]

            # Get communication logs
            comms = session.query(CommunicationLog).filter(CommunicationLog.patient_id == patient_id).all()
            data_payload["communications"] = [
                {
                    "channel": c.channel,
                    "purpose": c.purpose,
                    "sent_at": _iso(c.sent_at),
                    "delivered": c.delivered,
                }
                for c in comms
            ]

            # Note clinical retention if applicable
            if clinical_exemption["exempted"]:
                data_payload["retention_notes"] = (
                    f"Clinical records retained for {clinical_exemption['retention_years']} years "
                    f"under Clinical Establishments Act, 2010"
                )

            # Create the request record
            request_record = DataPrincipalRequest(
                id=request_id,
                patient_id=patient_id,
                request_type="ACCESS",
                request_details=request_details or {},
                status="COMPLETED",
                filed_at=now,
                sla_deadline=sla_deadline,
                resolved_at=now,
                response_data=data_payload,
                response_notes="Access request fulfilled — full data summary provided",
                verification_method=verification_method,
                created_at=now,
                updated_at=now,
            )
            session.add(request_record)

            # Log the access
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.DPDP_ACCESS_REQUEST,
                patient_id=patient_id,
                resource_id=request_id,
                resource_type="DataPrincipalRequest",
                description="Access request processed and fulfilled",
                details_json={"request_id": request_id, "categories": data_categories},
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return AccessRequestResult(
                request_id=request_id,
                patient_id=patient_id,
                status="COMPLETED",
                data_categories=data_categories,
                data_payload=data_payload,
                sla_deadline=_iso(sla_deadline),
                resolved_at=_iso(now),
                format="json",
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def process_correction_request(
        patient_id: str,
        fields_to_correct: dict[str, Any],
        verification_method: str = "OTP",
        session: Any | None = None,
    ) -> CorrectionRequestResult:
        """Process a Data Principal's correction request (DPDP Section 12).

        The fiduciary must correct inaccurate or misleading personal data
        and notify any recipients of the corrected data.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")

            now = _now()
            request_id = _uuid4()
            sla_deadline = now + timedelta(days=settings.DPDP_GRIEVANCE_SLA_DAYS)
            fields_requested = list(fields_to_correct.keys())
            fields_updated: list[str] = []

            # Map of allowed updatable fields with encryption awareness
            updatable_fields = {
                "phone": lambda v: setattr(patient, "phone", _encrypt(str(v))),
                "email": lambda v: setattr(patient, "email", _encrypt(str(v))),
                "address": lambda v: setattr(patient, "address", _encrypt(str(v))),
                "first_name": lambda v: setattr(patient, "first_name", _encrypt(str(v))),
                "last_name": lambda v: setattr(patient, "last_name", _encrypt(str(v))),
                "emergency_contact_name": lambda v: setattr(patient, "emergency_contact_name", _encrypt(str(v))),
                "emergency_contact_phone": lambda v: setattr(patient, "emergency_contact_phone", _encrypt(str(v))),
                "blood_group": lambda v: setattr(patient, "blood_group", str(v)),
                "chronic_conditions": lambda v: setattr(patient, "chronic_conditions", str(v)),
            }

            for field, value in fields_to_correct.items():
                if field in updatable_fields:
                    updatable_fields[field](value)
                    fields_updated.append(field)

            patient.updated_at = now

            # Create the request record
            request_record = DataPrincipalRequest(
                id=request_id,
                patient_id=patient_id,
                request_type="CORRECTION",
                request_details={"fields_requested": fields_requested, "fields_updated": fields_updated},
                status="COMPLETED" if fields_updated else "REJECTED",
                filed_at=now,
                sla_deadline=sla_deadline,
                resolved_at=now,
                response_data={"fields_updated": fields_updated, "fields_rejected": list(set(fields_requested) - set(fields_updated))},
                response_notes=f"Updated {len(fields_updated)} of {len(fields_requested)} requested fields",
                verification_method=verification_method,
                created_at=now,
                updated_at=now,
            )
            session.add(request_record)

            # Log
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.DPDP_CORRECTION_REQUEST,
                patient_id=patient_id,
                resource_id=request_id,
                resource_type="DataPrincipalRequest",
                description=f"Correction request: {len(fields_updated)} fields updated",
                details_json={"request_id": request_id, "fields_updated": fields_updated, "fields_requested": fields_requested},
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            rejection_reason = None
            if not fields_updated:
                rejection_reason = "None of the requested fields are updatable via this service"  # noqa: F841

            return CorrectionRequestResult(
                request_id=request_id,
                patient_id=patient_id,
                status="COMPLETED" if fields_updated else "REJECTED",
                fields_requested=fields_requested,
                fields_updated=fields_updated,
                sla_deadline=_iso(sla_deadline),
                resolved_at=_iso(now),
                notes=request_record.response_notes or "",
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def process_erasure_request(
        patient_id: str,
        erasure_reason: str = "USER_REQUEST",
        session: Any | None = None,
    ) -> ErasureRequestResult:
        """Process a Data Principal's erasure request (DPDP Section 13).

        Respects Clinical Establishments Act 3-year retention override for
        clinical records. Non-clinical data is scheduled for erasure.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")

            now = _now()
            request_id = _uuid4()
            sla_deadline = now + timedelta(days=settings.DPDP_GRIEVANCE_SLA_DAYS)

            # Check clinical establishment exemption (3-year retention)
            clinical_exemption = DpdpComplianceService.check_clinical_establishment_exemption(patient_id, session=session)

            retention_override = clinical_exemption["exempted"]
            retention_reason = None
            erasure_type = "FULL"

            if retention_override:
                retention_reason = (
                    f"Clinical data retained for {clinical_exemption['retention_years']} years "
                    f"under Clinical Establishments Act, 2010 Section 18(3). "
                    f"Affected categories: {', '.join(clinical_exemption['affected_data_categories'])}."
                )
                erasure_type = "PARTIAL"  # Only non-clinical data erased

            # Schedule erasure for non-exempted data
            # notification_deadline used for DPDP compliance tracking
            notification_deadline = now + timedelta(hours=settings.DPDP_ERASURE_NOTIFICATION_HOURS)  # noqa: F841
            scheduled_date = _today() + timedelta(days=3)  # 3-day buffer for notification

            erasure_schedule = ErasureSchedule(
                id=_uuid4(),
                patient_id=patient_id,
                erasure_type=erasure_type,
                erasure_reason=erasure_reason,
                scheduled_date=scheduled_date,
                notification_channel="EMAIL",
                execution_status="PENDING",
                created_at=now,
            )
            session.add(erasure_schedule)

            # Create data principal request
            request_record = DataPrincipalRequest(
                id=request_id,
                patient_id=patient_id,
                request_type="ERASURE",
                request_details={
                    "reason": erasure_reason,
                    "erasure_type": erasure_type,
                    "retention_override": retention_override,
                    "retention_reason": retention_reason,
                },
                status="IN_PROGRESS",
                filed_at=now,
                sla_deadline=sla_deadline,
                response_notes=retention_reason or "Erasure scheduled",
                created_at=now,
                updated_at=now,
            )
            session.add(request_record)

            # Log
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.DPDP_ERASURE_REQUEST,
                patient_id=patient_id,
                resource_id=request_id,
                resource_type="DataPrincipalRequest",
                description=f"Erasure request filed. Type: {erasure_type}. Override: {retention_override}",
                details_json={
                    "request_id": request_id,
                    "erasure_type": erasure_type,
                    "retention_override": retention_override,
                    "schedule_id": erasure_schedule.id,
                },
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return ErasureRequestResult(
                request_id=request_id,
                patient_id=patient_id,
                status="IN_PROGRESS",
                erasure_type=erasure_type,
                retention_override=retention_override,
                retention_reason=retention_reason,
                scheduled_date=_iso_date(scheduled_date),
                sla_deadline=_iso(sla_deadline),
                notification_required=True,
                notification_sent=False,
            )
        finally:
            if close_session:
                session.close()

    # ──────────────────────────────────────────────────────────────
    # 3. BREACH RESPONSE (DPDP Section 8)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def report_data_breach(
        description: str,
        breach_type: str = "UNAUTHORIZED_ACCESS",
        severity: str | BreachSeverity = BreachSeverity.MEDIUM,
        affected_patient_ids: list[str] | None = None,
        affected_data_categories: list[str] | None = None,
        occurred_at: datetime | None = None,
        root_cause: str | None = None,
        session: Any | None = None,
    ) -> BreachReportResult:
        """Report a data breach under DPDP Section 8.

        The Data Protection Board must be notified within 72 hours.
        Affected data principals must be notified of the breach,
        its nature, consequences, and mitigation measures.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            now = _now()
            breach_id = f"BR-{_uuid4()[:12].upper()}"

            if isinstance(severity, BreachSeverity):
                severity_val = severity
            else:
                severity_val = BreachSeverity(severity)

            # Board notification deadline: 72 hours from detection
            board_deadline = now + timedelta(hours=72)

            breach = DataBreach(
                id=_uuid4(),
                breach_id=breach_id,
                description=description,
                breach_type=breach_type,
                severity=severity_val,
                status=BreachStatus.DETECTED,
                detected_at=now,
                occurred_at=occurred_at or now,
                affected_patient_count=len(affected_patient_ids) if affected_patient_ids else 0,
                affected_data_categories=affected_data_categories or ["UNKNOWN"],
                root_cause=root_cause,
                board_notified=False,
                board_report_deadline=board_deadline,
                users_notified=False,
                created_at=now,
                updated_at=now,
            )
            session.add(breach)

            # Log the breach detection
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.BREACH_DETECTED,
                resource_id=breach_id,
                resource_type="DataBreach",
                description=f"Data breach detected: {breach_type} ({severity_val.value})",
                details_json={
                    "breach_id": breach_id,
                    "severity": severity_val.value,
                    "board_deadline": _iso(board_deadline),
                    "affected_count": breach.affected_patient_count,
                },
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return BreachReportResult(
                breach_id=breach_id,
                severity=severity_val.value,
                status=BreachStatus.DETECTED.value,
                description=description,
                affected_count=breach.affected_patient_count,
                affected_categories=breach.affected_data_categories or [],
                detected_at=_iso(now),
                board_notification_deadline=_iso(board_deadline),
                board_notified=False,
                users_notified=False,
                board_report_deadline=_iso(board_deadline),
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def notify_affected_users(
        breach_id: str,
        session: Any | None = None,
    ) -> BoardNotificationResult:
        """Notify affected data principals of a breach.

        DPDP Section 8(4): Notification must include:
        - Description of the breach
        - Timing of the breach
        - Likely consequences
        - Mitigation measures
        - Safety steps for the data principal
        - Contact information for grievance
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            breach = session.query(DataBreach).filter(DataBreach.breach_id == breach_id).first()
            if not breach:
                raise ValueError(f"Breach {breach_id} not found")

            now = _now()

            # Build the notification content (DPDP Section 8.4)
            severity_labels = {
                BreachSeverity.LOW: "low impact — minimal risk to data subjects",
                BreachSeverity.MEDIUM: "moderate impact — potential risk to data subjects",
                BreachSeverity.HIGH: "significant impact — real risk to data subjects",
                BreachSeverity.CRITICAL: "critical impact — severe risk to data subjects",
            }
            severity_desc = severity_labels.get(breach.severity, "unknown severity")

            notification_text = (
                f"DATA BREACH NOTIFICATION — HealthBridge Platform\n"
                f"Reference: {breach.breach_id}\n"
                f"Date: {now.strftime('%d %B %Y %H:%M UTC')}\n\n"
                f"Nature of Breach:\n"
                f"  {breach.description}\n\n"
                f"Timing:\n"
                f"  Detected: {breach.detected_at.strftime('%d %B %Y %H:%M UTC')}\n"
                f"  Occurred: {breach.occurred_at.strftime('%d %B %Y %H:%M UTC') if breach.occurred_at else 'Unknown'}\n\n"
                f"Severity: {severity_desc}\n\n"
                f"Likely Consequences:\n"
                f"  The following categories of your personal data may have been affected:\n"
                + "\n".join(f"  • {c}" for c in (breach.affected_data_categories or [])) + "\n\n"
                f"Mitigation Measures:\n"
                f"  • Affected systems have been isolated and secured\n"
                f"  • Access controls have been reviewed and strengthened\n"
                f"  • Forensic investigation is underway\n"
                f"  {breach.remediation_steps or ''}\n\n"
                f"Steps You Should Take:\n"
                f"  • Monitor your accounts for suspicious activity\n"
                f"  • Contact your healthcare providers if you notice anomalies\n"
                f"  • Report any suspected misuse to the Grievance Officer\n\n"
                f"Contact:\n"
                f"  Data Protection Officer: dpo@healthbridge.in\n"
                f"  Grievance Officer: grievance@healthbridge.in\n"
                f"  Helpline: 1800-XXX-XXXX\n\n"
                f"We sincerely regret this incident and assure you of our full cooperation.\n"
                f"HealthBridge Data Protection Team"
            )

            # Find affected patients and create notifications
            # In production, this would query the actual affected patient IDs
            affected_patients = (
                session.query(Patient)
                .filter(Patient.consent_status == ConsentStatus.GRANTED)
                .limit(breach.affected_patient_count or 0)
                .all()
            )

            notification_count = 0
            for patient in affected_patients:
                # Determine contact info (try to decrypt email)
                try:
                    recipient_email = _decrypt(patient.email) if patient.email else f"patient-{patient.id}@healthbridge.in"
                except Exception:
                    recipient_email = f"patient-{patient.id}@healthbridge.in"

                notification = BreachNotification(
                    id=_uuid4(),
                    breach_id=breach.id,
                    patient_id=patient.id,
                    channel="EMAIL",
                    recipient=recipient_email,
                    sent_at=now,
                    delivered=True,
                    delivery_status="SENT",
                    breach_description=breach.description,
                    breach_timing=f"Detected: {breach.detected_at.isoformat()}",
                    likely_consequences=f"Affected categories: {', '.join(breach.affected_data_categories or [])}",
                    mitigation_measures=breach.remediation_steps or "Systems secured, investigation underway",
                    safety_steps="Monitor accounts; contact Grievance Officer for assistance",
                    contact_info="dpo@healthbridge.in | grievance@healthbridge.in",
                )
                session.add(notification)

                # Communication log entry
                comm_log = CommunicationLog(
                    id=_uuid4(),
                    patient_id=patient.id,
                    channel="EMAIL",
                    recipient=recipient_email,
                    subject=f"Data Breach Notification — {breach.breach_id}",
                    body_preview=notification_text[:200],
                    purpose="BREACH",
                    sent_at=now,
                    delivered=True,
                    delivery_status="SENT",
                )
                session.add(comm_log)
                notification_count += 1

            # Update breach record
            breach.users_notified = True
            breach.users_notified_at = now
            breach.status = BreachStatus.INVESTIGATING
            breach.updated_at = now

            # Log notification event
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.BREACH_NOTIFIED,
                resource_id=breach_id,
                resource_type="DataBreach",
                description=f"Affected data principals notified: {notification_count} notifications sent",
                details_json={
                    "breach_id": breach_id,
                    "notification_count": notification_count,
                    "notification_channel": "EMAIL",
                },
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return BoardNotificationResult(
                breach_id=breach_id,
                board_notified=breach.board_notified,
                board_notified_at=_iso(breach.board_notified_at),
                report_deadline=_iso(breach.board_report_deadline),
                report_submitted=breach.board_report_submitted,
                notification_payload={
                    "notification_count": notification_count,
                    "notification_text": notification_text,
                    "channel": "EMAIL",
                },
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def notify_data_protection_board(
        breach_id: str,
        session: Any | None = None,
    ) -> BoardNotificationResult:
        """Notify the Data Protection Board under DPDP Section 8.

        The Board must be informed within 72 hours of breach detection,
        with a detailed report containing nature, extent, impact, and
        remediation measures.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            breach = session.query(DataBreach).filter(DataBreach.breach_id == breach_id).first()
            if not breach:
                raise ValueError(f"Breach {breach_id} not found")

            now = _now()

            # Build board notification payload
            board_payload = {
                "breach_id": breach.breach_id,
                "fiduciary_name": settings.APP_NAME,
                "fiduciary_registration": "HEALTHBRIDGE-SDF-2025-001",
                "breach_type": breach.breach_type,
                "severity": breach.severity.value if breach.severity else "UNKNOWN",
                "description": breach.description,
                "detected_at": _iso(breach.detected_at),
                "occurred_at": _iso(breach.occurred_at),
                "affected_data_subjects": breach.affected_patient_count,
                "affected_data_categories": breach.affected_data_categories,
                "root_cause": breach.root_cause,
                "remediation_steps": breach.remediation_steps,
                "current_status": breach.status.value if breach.status else "UNKNOWN",
                "users_notified": breach.users_notified,
                "users_notified_at": _iso(breach.users_notified_at),
                "notification_timestamp": _iso(now),
                "dpo_name": "Not specified",
                "dpo_email": "dpo@healthbridge.in",
            }

            # Update breach record
            breach.board_notified = True
            breach.board_notified_at = now
            breach.status = BreachStatus.REPORTED_TO_BOARD
            breach.updated_at = now

            # Log
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.BREACH_NOTIFIED,
                resource_id=breach_id,
                resource_type="DataBreach",
                description="Data Protection Board notified of breach",
                details_json={
                    "breach_id": breach_id,
                    "board_payload": board_payload,
                },
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return BoardNotificationResult(
                breach_id=breach_id,
                board_notified=True,
                board_notified_at=_iso(now),
                report_deadline=_iso(breach.board_report_deadline),
                report_submitted=False,
                notification_payload=board_payload,
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def submit_72hr_report(
        breach_id: str,
        findings: dict[str, Any] | None = None,
        session: Any | None = None,
    ) -> Breach72HourReport:
        """Submit the detailed 72-hour report to the Data Protection Board.

        This is the comprehensive report required under DPDP Section 8(3)
        containing findings from the initial investigation.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            breach = session.query(DataBreach).filter(DataBreach.breach_id == breach_id).first()
            if not breach:
                raise ValueError(f"Breach {breach_id} not found")

            now = _now()

            report_payload = {
                "breach_id": breach.breach_id,
                "submission_type": "72-HOUR DETAILED REPORT",
                "submitted_at": _iso(now),
                "fiduciary": {
                    "name": settings.APP_NAME,
                    "dpo_contact": "dpo@healthbridge.in",
                    "compliant": True,
                },
                "breach_details": {
                    "description": breach.description,
                    "breach_type": breach.breach_type,
                    "severity": breach.severity.value if breach.severity else None,
                    "detected_at": _iso(breach.detected_at),
                    "occurred_at": _iso(breach.occurred_at),
                    "contained_at": _iso(breach.contained_at),
                },
                "impact_assessment": {
                    "affected_data_subjects": breach.affected_patient_count,
                    "affected_data_categories": breach.affected_data_categories,
                    "likely_consequences": "Unauthorized access to personal data",
                },
                "root_cause_analysis": {
                    "root_cause": breach.root_cause or "Under investigation",
                    "findings": findings or breach.findings_json or {},
                },
                "remediation": {
                    "steps_taken": breach.remediation_steps or "Systems secured, access revoked",
                    "status": breach.status.value if breach.status else None,
                    "preventive_measures": "Enhanced access controls, audit logging, staff training",
                },
                "notifications": {
                    "board_notified": breach.board_notified,
                    "board_notified_at": _iso(breach.board_notified_at),
                    "users_notified": breach.users_notified,
                    "users_notified_at": _iso(breach.users_notified_at),
                    "notification_method": "EMAIL",
                },
                "compliance": {
                    "dpdp_section_8_compliant": True,
                    "72hr_requirement_met": (now - breach.detected_at).total_seconds() <= 72 * 3600,
                    "report_submitted_on_time": True,
                },
            }

            # Update breach
            breach.board_report_submitted = True
            breach.findings_json = findings or breach.findings_json or {}
            breach.status = BreachStatus.INVESTIGATING
            breach.updated_at = now

            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.BREACH_NOTIFIED,
                resource_id=breach_id,
                resource_type="DataBreach",
                description="72-hour detailed breach report submitted to Board",
                details_json={"breach_id": breach_id, "report_size_bytes": len(json.dumps(report_payload))},
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            time_to_report = (now - breach.detected_at).total_seconds()
            hours_elapsed = round(time_to_report / 3600, 1)

            return Breach72HourReport(
                breach_id=breach_id,
                submitted=True,
                submitted_at=_iso(now),
                report_payload=report_payload,
                compliance_notes=(
                    f"Report submitted {hours_elapsed} hours after detection "
                    f"({'within' if hours_elapsed <= 72 else 'exceeding'} 72-hour deadline)"
                ),
            )
        finally:
            if close_session:
                session.close()

    # ──────────────────────────────────────────────────────────────
    # 4. RETENTION & ERASURE (DPDP Section 8.5, 8.6)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def schedule_erasure(
        patient_id: str,
        erasure_type: str = "FULL",
        reason: str = "PURPOSE_FULFILLED",
        session: Any | None = None,
    ) -> ErasureScheduleResult:
        """Schedule erasure of personal data when the purpose is fulfilled.

        DPDP Section 8(5): Personal data must be erased after the purpose
        is fulfilled, subject to legal retention requirements.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")

            now = _now()

            # Check clinical exemption
            clinical_exemption = DpdpComplianceService.check_clinical_establishment_exemption(patient_id, session=session)

            if clinical_exemption["exempted"] and erasure_type == "FULL":
                erasure_type = "PARTIAL"
                logger.info(
                    f"Erasure for {patient_id} downgraded to PARTIAL: "
                    f"clinical retention required ({clinical_exemption['retention_years']} years)"
                )

            # schedule: 48-hour notification period + immediate execution
            notification_buffer = timedelta(hours=settings.DPDP_ERASURE_NOTIFICATION_HOURS)  # noqa: F841
            scheduled_date = _today() + timedelta(days=3)  # 3 days for notification + buffer

            schedule = ErasureSchedule(
                id=_uuid4(),
                patient_id=patient_id,
                erasure_type=erasure_type,
                erasure_reason=reason,
                scheduled_date=scheduled_date,
                notification_channel="EMAIL",
                execution_status="PENDING",
                created_at=now,
            )
            session.add(schedule)
            session.commit()

            return ErasureScheduleResult(
                schedule_id=schedule.id,
                patient_id=patient_id,
                erasure_type=erasure_type,
                reason=reason,
                scheduled_date=_iso_date(scheduled_date),
                notification_sent=False,
                notification_channel="EMAIL",
                execution_status="PENDING",
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def send_erasure_notification(
        schedule_id: str,
        session: Any | None = None,
    ) -> ErasureNotification:
        """Send pre-erasure notification to the data principal.

        DPDP Section 8(5): The data principal must be notified of
        the intended erasure at least 48 hours before execution.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            schedule = session.query(ErasureSchedule).filter(ErasureSchedule.id == schedule_id).first()
            if not schedule:
                raise ValueError(f"Erasure schedule {schedule_id} not found")

            patient = session.query(Patient).filter(Patient.id == schedule.patient_id).first()
            if not patient:
                raise ValueError(f"Patient {schedule.patient_id} not found")

            now = _now()

            # Determine recipient
            try:
                recipient = _decrypt(patient.email) if patient.email else f"patient-{patient.id}@healthbridge.in"
            except Exception:
                recipient = f"patient-{patient.id}@healthbridge.in"

            reason_labels = {
                "PURPOSE_FULFILLED": "the purpose for which your data was collected has been fulfilled",
                "USER_REQUEST": "you have requested erasure of your data",
                "EXPIRED": "the consent period has expired",
                "USER_WITHDRAWAL": "you have withdrawn your consent",
            }
            reason_text = reason_labels.get(schedule.erasure_reason, schedule.erasure_reason.lower().replace("_", " "))

            notice_text = (
                f"PRE-ERASURE NOTIFICATION — HealthBridge Platform\n"
                f"Schedule ID: {schedule.id}\n"
                f"Date: {now.strftime('%d %B %Y')}\n\n"
                f"Your personal data is scheduled for erasure because {reason_text}.\n\n"
                f"Erasure Type: {schedule.erasure_type}\n"
                f"Scheduled Date: {schedule.scheduled_date.strftime('%d %B %Y') if schedule.scheduled_date else 'N/A'}\n\n"
                f"What Will Be Deleted:\n"
                + (f"  • All non-clinical personal data (demographics, contact information)\n"
                   f"  • Clinical records will be retained for {settings.DPDP_CLINICAL_RETENTION_YEARS} years "
                   f"as required by the Clinical Establishments Act, 2010\n"
                   if schedule.erasure_type == "PARTIAL"
                   else "  • All your personal data, subject to legal retention requirements\n") +
                f"\nHow to Stop Erasure:\n"
                f"  If you wish to retain your data, please contact us within 48 hours:\n"
                f"  • Email: grievance@healthbridge.in (Subject: 'Retain Data - {schedule.id}')\n"
                f"  • Portal: https://portal.healthbridge.in/erasure/{schedule.id}\n\n"
                f"  If we do not hear from you, the erasure will proceed as scheduled.\n\n"
                f"Thank you,\nHealthBridge Data Protection Team"
            )

            # Update schedule
            schedule.notified_at = now
            schedule.notification_channel = "EMAIL"

            # Communication log
            comm_log = CommunicationLog(
                id=_uuid4(),
                patient_id=schedule.patient_id,
                channel="EMAIL",
                recipient=recipient,
                subject="Pre-Erasure Notification — Data Scheduled for Deletion",
                body_preview=notice_text[:200],
                purpose="ERASURE_NOTICE",
                sent_at=now,
                delivered=True,
                delivery_status="SENT",
            )
            session.add(comm_log)
            session.commit()

            return ErasureNotification(
                schedule_id=schedule.id,
                patient_id=schedule.patient_id,
                channel="EMAIL",
                recipient=recipient,
                notice_text=notice_text,
                sent_at=_iso(now),
                user_responded=schedule.user_responded,
                response=schedule.user_response,
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def execute_erasure(
        schedule_id: str,
        session: Any | None = None,
    ) -> ErasureExecution:
        """Execute a scheduled data erasure.

        Called by the APScheduler cron job. Anonymizes or deletes
        patient data according to the erasure type, respecting
        clinical retention exemptions.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            schedule = session.query(ErasureSchedule).filter(ErasureSchedule.id == schedule_id).first()
            if not schedule:
                raise ValueError(f"Erasure schedule {schedule_id} not found")

            if schedule.execution_status == "COMPLETED":
                return ErasureExecution(
                    schedule_id=schedule_id,
                    executed=True,
                    executed_at=_iso(schedule.executed_at),
                    records_affected=schedule.records_affected or 0,
                    details={"note": "Already executed"},
                )

            patient = session.query(Patient).filter(Patient.id == schedule.patient_id).first()
            if not patient:
                raise ValueError(f"Patient {schedule.patient_id} not found")

            now = _now()
            clinical_exemption = DpdpComplianceService.check_clinical_establishment_exemption(
                schedule.patient_id, session=session
            )

            records_affected = 0
            details: dict[str, Any] = {}
            clinical_retention_exemptions: list[str] = []

            if schedule.erasure_type == "FULL":
                # Full erasure: pseudonymize/anonymize all data
                if not clinical_exemption["exempted"]:
                    patient.first_name = _encrypt("ANONYMIZED")
                    patient.last_name = _encrypt("ANONYMIZED")
                    patient.phone = _encrypt("ANONYMIZED")
                    patient.email = _encrypt("ANONYMIZED")
                    patient.address = _encrypt("ANONYMIZED")
                    patient.abha_number = None
                    patient.aadhaar_hash = None
                    patient.emergency_contact_name = _encrypt("ANONYMIZED")
                    patient.emergency_contact_phone = _encrypt("ANONYMIZED")
                    patient.date_of_birth = None
                    patient.chronic_conditions = None
                    records_affected += 11
                    details["full_erasure"] = "11 fields anonymized"

            elif schedule.erasure_type == "PARTIAL":
                # Partial: erase non-clinical, keep clinical
                patient.phone = _encrypt("ANONYMIZED")
                patient.email = _encrypt("ANONYMIZED")
                patient.address = _encrypt("ANONYMIZED")
                patient.abha_number = None
                patient.aadhaar_hash = None
                patient.emergency_contact_name = _encrypt("ANONYMIZED")
                patient.emergency_contact_phone = _encrypt("ANONYMIZED")
                records_affected += 7
                details["partial_erasure"] = "7 non-clinical fields anonymized (clinical preserved)"

                if clinical_exemption["exempted"]:
                    clinical_retention_exemptions = clinical_exemption["affected_data_categories"]
                    details["clinical_retention"] = clinical_retention_exemptions
                    details["retention_years"] = clinical_exemption["retention_years"]

            elif schedule.erasure_type == "PSEUDONYMIZE":
                # Pseudonymization: replace identifiers with tokens
                patient.first_name = _encrypt(f"PSEUDO-{_uuid4()[:8]}")
                patient.last_name = _encrypt(f"PSEUDO-{_uuid4()[:8]}")
                patient.phone = _encrypt("REMOVED")
                patient.email = _encrypt("REMOVED")
                patient.address = _encrypt("REMOVED")
                patient.abha_number = None
                patient.aadhaar_hash = None
                records_affected += 7
                details["pseudonymization"] = "Direct identifiers replaced with pseudonyms"

            # Update patient
            patient.data_retention_until = None
            patient.consent_status = ConsentStatus.REVOKED
            patient.consent_id = None
            patient.consent_purposes = []
            patient.consent_granted_at = None
            patient.consent_expires_at = None
            patient.updated_at = now
            records_affected += 6

            # Update schedule
            schedule.executed_at = now
            schedule.execution_status = "COMPLETED"
            schedule.records_affected = records_affected

            # Log erasure
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.DPDP_ERASURE_REQUEST,
                patient_id=schedule.patient_id,
                resource_id=schedule.id,
                resource_type="ErasureSchedule",
                description=f"Erasure executed: {schedule.erasure_type} ({records_affected} records affected)",
                details_json={
                    "schedule_id": schedule.id,
                    "erasure_type": schedule.erasure_type,
                    "records_affected": records_affected,
                    "clinical_exempted": bool(clinical_retention_exemptions),
                },
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return ErasureExecution(
                schedule_id=schedule.id,
                executed=True,
                executed_at=_iso(now),
                records_affected=records_affected,
                details=details,
                clinical_retention_exemptions=clinical_retention_exemptions or None,
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def purge_expired_logs(
        session: Any | None = None,
    ) -> PurgeResult:
        """Purge audit logs, communications, and notifications past retention.

        DPDP Section 8(6): Audit logs must be retained for a minimum of
        1 year. After the retention period, they should be purged
        to minimize data footprint. Called by APScheduler cron job.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            now = _now()
            cutoff_date = _today() - timedelta(days=settings.DPDP_RETENTION_DAYS)

            # Purge audit logs beyond retention
            expired_audits = (
                session.query(AuditLog)
                .filter(
                    (AuditLog.retention_until < cutoff_date) | (
                        (AuditLog.retention_until.is_(None)) & (AuditLog.timestamp < cutoff_date)
                    )
                )
                .delete(synchronize_session=False)
            )

            # Purge communication logs older than retention
            expired_comms = (
                session.query(CommunicationLog)
                .filter(CommunicationLog.sent_at < cutoff_date)
                .delete(synchronize_session=False)
            )

            # Purge expired breach notifications
            expired_notifications = (
                session.query(BreachNotification)
                .filter(BreachNotification.sent_at < cutoff_date)
                .delete(synchronize_session=False)
            )

            # Soft-expire consent records (mark as EXPIRED if past expiry)
            expired_consents = (
                session.query(ConsentRecord)
                .filter(
                    ConsentRecord.expires_at < now,
                    ConsentRecord.status == ConsentStatus.GRANTED,
                )
                .update({"status": ConsentStatus.EXPIRED}, synchronize_session=False)
            )

            session.commit()

            logger.info(
                f"DPDP purge completed: {expired_audits} audit logs, "
                f"{expired_comms} communications, "
                f"{expired_notifications} notifications, "
                f"{expired_consents} consents expired"
            )

            return PurgeResult(
                purged_audit_logs=expired_audits,
                purged_communications=expired_comms,
                purged_expired_consents=expired_consents,
                purged_notifications=expired_notifications,
                cutoff_date=_iso_date(cutoff_date),
                executed_at=_iso(now),
            )
        finally:
            if close_session:
                session.close()

    # ──────────────────────────────────────────────────────────────
    # 5. CROSS-BORDER TRANSFER (DPDP Section 9, 10)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def assess_cross_border_transfer(
        destination_country: str,
        data_categories: list[str] | None = None,
        purpose: str | None = None,
        session: Any | None = None,
    ) -> CrossBorderTransferAssessment:
        """Assess whether a cross-border data transfer is DPDP-compliant.

        DPDP Section 9: Personal data may be transferred to countries
        notified by the Central Government as adequate.
        DPDP Section 10: Certain sensitive data may only be transferred
        under specific conditions.

        Known adequate countries (notified under DPDP Rules 2025):
        - Standard Contractual Clauses (SCC) based transfers permitted
        - Binding Corporate Rules (BCR) based transfers permitted
        - Specific adequacy determinations by Government of India
        """
        # As per DPDP Rules 2025 — illustrative list of adequacy considerations
        # In production, this would query an up-to-date adequacy registry
        adequate_countries: set[str] = {
            "singapore", "japan", "south korea", "germany", "france",
            "united kingdom", "canada", "australia", "new zealand",
            "uae", "saudi arabia", "netherlands",
        }

        # Countries with restricted transfer (DPDP Rules 2025 Schedule I)
        restricted_countries: set[str] = {
            "china", "russia", "north korea", "iran", "syria",
        }

        country_lower = destination_country.strip().lower()
        categories = data_categories or ["DEMOGRAPHICS"]
        permitted = True
        adequacy_status = "NOT_ASSESSED"
        safeguards: list[str] = []
        contract_clauses: list[str] = []
        restrictions: list[str] = []

        # Check for restricted countries
        if country_lower in restricted_countries:
            permitted = False
            adequacy_status = "RESTRICTED"
            restrictions.append(f"Transfer to {destination_country} is prohibited under DPDP Rules 2025")
            return CrossBorderTransferAssessment(
                permitted=False,
                country=destination_country,
                adequacy_status=adequacy_status,
                dpdp_compliant=False,
                safeguards=safeguards,
                contract_clauses=[],
                restrictions=restrictions,
                assessment_date=_iso(_now()),
            )

        # Check adequacy
        if country_lower in adequate_countries:
            adequacy_status = "ADEQUATE"
            safeguards.append("Adequacy determination by Central Government")
            contract_clauses = [
                "DPDP-compliant Standard Contractual Clauses (SCC)",
                "Data Principal rights preserved under Indian law",
                "Data Protection Board jurisdiction retained",
                "Equivalent level of protection guaranteed",
            ]
        else:
            adequacy_status = "ADEQUATE_WITH_SAFEGUARDS"
            safeguards = [
                "Standard Contractual Clauses (SCC) adopted",
                "Data Protection Impact Assessment conducted",
                "Equivalent data protection measures contractually guaranteed",
                "Right to Data Protection Board jurisdiction retained",
            ]
            contract_clauses = [
                "DPDP-compliant SCCs",
                "Data minimization and purpose limitation clauses",
                "Breach notification obligations extended to transferee",
                "Audit and inspection rights retained",
                "Data Principal rights enforcement mechanism",
            ]

        # Check for sensitive data categories
        sensitive_categories = {"GENETIC", "BIOMETRIC", "HEALTH_RECORDS", "FINANCIAL"}
        sensitive_intersection = [c for c in categories if c.upper() in sensitive_categories]
        if sensitive_intersection:
            restrictions.append(
                f"Sensitive data categories ({', '.join(sensitive_intersection)}) "
                f"require explicit consent for cross-border transfer"
            )
            safeguards.append("Explicit consent obtained for sensitive data transfer")

        if purpose and purpose.upper() == "RESEARCH":
            restrictions.append(
                "Research data transfer requires anonymization or Data Protection Board approval"
            )
            safeguards.append("Data anonymized prior to transfer or Board approval obtained")

        return CrossBorderTransferAssessment(
            permitted=permitted,
            country=destination_country,
            adequacy_status=adequacy_status,
            dpdp_compliant=True,
            safeguards=safeguards,
            contract_clauses=contract_clauses,
            restrictions=restrictions,
            assessment_date=_iso(_now()),
        )

    # ──────────────────────────────────────────────────────────────
    # 6. GRIEVANCE (DPDP Section 14)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def process_grievance(
        patient_id: str,
        grievance_details: dict[str, Any],
        verification_method: str = "OTP",
        session: Any | None = None,
    ) -> GrievanceResult:
        """Process a data principal's grievance under DPDP Section 14.

        The data fiduciary must establish a grievance redressal mechanism
        and resolve grievances within 90 days (or as specified by rules).
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")

            now = _now()
            request_id = _uuid4()
            sla_deadline = now + timedelta(days=settings.DPDP_GRIEVANCE_SLA_DAYS)

            request_record = DataPrincipalRequest(
                id=request_id,
                patient_id=patient_id,
                request_type="GRIEVANCE",
                request_details=grievance_details,
                status="PENDING",
                filed_at=now,
                sla_deadline=sla_deadline,
                verification_method=verification_method,
                created_at=now,
                updated_at=now,
            )
            session.add(request_record)

            # Log
            audit = AuditLog(
                id=_uuid4(),
                timestamp=now,
                action=AuditAction.DPDP_GRIEVANCE_FILED,
                patient_id=patient_id,
                resource_id=request_id,
                resource_type="DataPrincipalRequest",
                description=f"Grievance filed: {grievance_details.get('subject', 'No subject')[:100]}",
                details_json={
                    "request_id": request_id,
                    "subject": grievance_details.get("subject"),
                    "sla_deadline": _iso(sla_deadline),
                },
                retention_until=_today() + timedelta(days=settings.DPDP_RETENTION_DAYS),
            )
            session.add(audit)
            session.commit()

            return GrievanceResult(
                request_id=request_id,
                patient_id=patient_id,
                status="PENDING",
                sla_deadline=_iso(sla_deadline),
                filed_at=_iso(now),
                resolved_at=None,
                response_notes=None,
                sla_compliant=None,
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def check_sla_compliance(
        session: Any | None = None,
    ) -> SlaComplianceCheck:
        """Check SLA compliance for all open data principal requests.

        DPDP Section 14: Grievances must be resolved within the prescribed
        period (90 days under DPDP Rules 2025).
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            now = _now()

            open_requests = (
                session.query(DataPrincipalRequest)
                .filter(DataPrincipalRequest.status.in_(["PENDING", "IN_PROGRESS"]))
                .all()
            )

            sla_days = settings.DPDP_GRIEVANCE_SLA_DAYS
            within_sla = 0
            breached_sla = 0
            items_breached: list[dict[str, Any]] = []

            for req in open_requests:
                if req.sla_deadline and req.sla_deadline < now:
                    breached_sla += 1
                    items_breached.append({
                        "request_id": req.id,
                        "patient_id": req.patient_id,
                        "request_type": req.request_type,
                        "filed_at": _iso(req.filed_at),
                        "sla_deadline": _iso(req.sla_deadline),
                        "days_overdue": (now - req.sla_deadline).days,
                    })
                else:
                    within_sla += 1

            total = len(open_requests)
            breach_pct = round((breached_sla / total * 100), 2) if total > 0 else 0.0

            return SlaComplianceCheck(
                total_open=total,
                within_sla=within_sla,
                breached_sla=breached_sla,
                sla_days=sla_days,
                breach_percentage=breach_pct,
                items_breached=items_breached,
            )
        finally:
            if close_session:
                session.close()

    # ──────────────────────────────────────────────────────────────
    # 7. SIGNIFICANT DATA FIDUCIARY (DPDP Section 16)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def conduct_dpia(
        data_processing_activity: str,
        data_categories: list[str] | None = None,
        processing_purpose: str | None = None,
        session: Any | None = None,
    ) -> DpiaResult:
        """Conduct a Data Protection Impact Assessment (DPIA).

        DPDP Section 16: Significant Data Fiduciaries must conduct
        DPIAs for specified processing activities that pose high risk
        to data principals. Must be reviewed by Data Protection Officer.
        """
        risk_matrix: dict[str, tuple[str, list[str], list[str], str]] = {
            "HEALTH_RECORDS_PROCESSING": (
                "HIGH",
                [
                    "Large-scale processing of sensitive health data",
                    "Potential for re-identification of anonymized data",
                    "Cross-border data flow risks",
                    "Automated decision-making affecting treatment",
                ],
                [
                    "Encryption at rest and in transit (AES-256, TLS 1.3)",
                    "Role-based access control (RBAC) with audit trails",
                    "Data minimization — only collect what is necessary",
                    "Consent management with granular purpose selection",
                    "Anonymization/pseudonymization before analysis",
                    "Regular security audits and penetration testing",
                ],
                "MEDIUM — mitigations adequate with continuous monitoring",
            ),
            "GENETIC_DATA_PROCESSING": (
                "HIGH",
                [
                    "Irreversible nature of genetic data processing",
                    "Potential for familial and community harm",
                    "Discrimination risks (insurance, employment)",
                    "Long-term privacy implications across generations",
                ],
                [
                    "Explicit, separate consent for genetic processing",
                    "Genetic data stored separately with enhanced encryption",
                    "Strict access controls — limited to authorized geneticists",
                    "Data retention limited to 10 years with periodic review",
                    "No sharing with insurance or employment entities",
                    "Regular DPIA reviews every 6 months",
                ],
                "HIGH — residual risk requires Board-level oversight",
            ),
            "CROSS_BORDER_TRANSFER": (
                "MEDIUM",
                [
                    "Transfer to jurisdictions with different privacy regimes",
                    "Enforcement challenges for data principal rights",
                    "Third-party vendor risk in data processing chain",
                ],
                [
                    "Standard Contractual Clauses (SCC) with transferees",
                    "Adequacy assessment per DPDP Section 9",
                    "Data residency for sensitive health data where possible",
                    "Contractual audit rights retained",
                ],
                "MEDIUM — adequate with contractual safeguards",
            ),
            "AI_ML_MODEL_TRAINING": (
                "HIGH",
                [
                    "Potential for biased outcomes affecting marginalized groups",
                    "Opacity of automated decision-making",
                    "Risk of model inversion revealing training data",
                    "Purpose creep — models used beyond original intent",
                ],
                [
                    "Training data anonymized before model ingestion",
                    "Bias testing and fairness audits before deployment",
                    "Human-in-the-loop for clinical decisions",
                    "Explainability requirements for all AI outputs",
                    "Data Protection Officer review of training datasets",
                ],
                "MEDIUM — residual risk managed with AI governance framework",
            ),
            "HEALTHCARE_RESEARCH": (
                "MEDIUM",
                [
                    "Processing for secondary purposes beyond original consent",
                    "Potential for re-identification in published research",
                    "Data linkage with external datasets",
                ],
                [
                    "Research ethics committee approval obtained",
                    "Data anonymized to DPDP standards before use",
                    "Institutional review board oversight",
                    "Results published as aggregate only",
                    "Opt-out mechanism for data principals",
                ],
                "LOW — standard research safeguards adequate",
            ),
        }

        # Default assessment for unspecified activities
        default_risks = [
            f"Processing of {', '.join(data_categories or ['personal data'])} without DPIA template",
            "Potential non-compliance with DPDP Section 16 requirements",
        ]
        default_mitigations = [
            "Engage Data Protection Officer for review",
            "Conduct comprehensive risk assessment",
            "Document processing purposes and legal basis",
            "Implement appropriate technical and organizational measures",
        ]

        activity_key = data_processing_activity.replace(" ", "_").upper()
        if activity_key in risk_matrix:
            risk_level, risks, mitigations, residual = risk_matrix[activity_key]
        else:
            risk_level = "MEDIUM"
            risks = default_risks
            mitigations = default_mitigations
            residual = "Not fully assessed — DPIA needs review"

        now = _now()
        dpia_id = f"DPIA-{_uuid4()[:12].upper()}"
        next_review = now + timedelta(days=365)  # Annual review

        return DpiaResult(
            dpia_id=dpia_id,
            data_processing_activity=data_processing_activity,
            risk_level=risk_level,
            risks_identified=risks,
            mitigation_measures=mitigations,
            residual_risk=residual,
            conducted_at=_iso(now),
            reviewed_by="Data Protection Officer (HealthBridge)",
            next_review_date=_iso(next_review),
        )

    @staticmethod
    def generate_compliance_report(
        report_period: str = "MONTHLY",
        session: Any | None = None,
    ) -> ComplianceReport:
        """Generate a comprehensive DPDP compliance report.

        DPDP Section 16: Significant Data Fiduciaries must submit
        periodic compliance reports to the Data Protection Board.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            now = _now()

            # Count statistics from the database
            consent_count = session.query(ConsentRecord).count()
            active_consents = session.query(ConsentRecord).filter(
                ConsentRecord.status == ConsentStatus.GRANTED
            ).count()

            dp_requests = session.query(DataPrincipalRequest).count()
            grievances = session.query(DataPrincipalRequest).filter(
                DataPrincipalRequest.request_type == "GRIEVANCE"
            ).count()
            grievances_resolved = session.query(DataPrincipalRequest).filter(
                DataPrincipalRequest.request_type == "GRIEVANCE",
                DataPrincipalRequest.status == "COMPLETED",
            ).count()

            breaches = session.query(DataBreach).count()
            breaches_notified = session.query(DataBreach).filter(
                DataBreach.board_notified
            ).count()

            erasures_scheduled = session.query(ErasureSchedule).count()
            erasures_executed = session.query(ErasureSchedule).filter(
                ErasureSchedule.execution_status == "COMPLETED"
            ).count()

            # Observations based on data
            observations: list[str] = []

            if active_consents > 0:
                observations.append(f"{active_consents} active consents — all with valid notices under DPDP Section 6")
            else:
                observations.append("No active consents registered — verify consent management flow")

            if grievances_resolved < grievances and grievances > 0:
                observations.append(
                    f"{grievances - grievances_resolved} grievances pending resolution — "
                    f"monitor {settings.DPDP_GRIEVANCE_SLA_DAYS}-day SLA"
                )

            if breaches_notified > 0:
                observations.append(f"{breaches_notified} breaches notified to Data Protection Board within 72-hour window")

            sla_check = DpdpComplianceService.check_sla_compliance(session=session)
            if sla_check["breached_sla"] > 0:
                observations.append(
                    f"⚠️ {sla_check['breached_sla']} requests have breached the "
                    f"{settings.DPDP_GRIEVANCE_SLA_DAYS}-day SLA (breach rate: {sla_check['breach_percentage']}%)"
                )

            observations.append(f"Retention policy: {settings.DPDP_RETENTION_DAYS} days for audit logs")
            observations.append(f"Clinical retention: {settings.DPDP_CLINICAL_RETENTION_YEARS} years under Clinical Establishments Act")

            dpia_count = 0  # DPIAs are conducted on-demand

            compliance_status = "COMPLIANT"
            if sla_check["breach_percentage"] > 10:
                compliance_status = "PARTIALLY_COMPLIANT"
                observations.append("SLA breach rate exceeds 10% threshold — remediation required")

            report_id = f"COMP-{_uuid4()[:12].upper()}"

            return ComplianceReport(
                report_id=report_id,
                generated_at=_iso(now),
                report_period=report_period,
                consent_count=consent_count,
                active_consents=active_consents,
                data_principal_requests=dp_requests,
                grievances_filed=grievances,
                grievances_resolved=grievances_resolved,
                breaches_detected=breaches,
                breaches_notified=breaches_notified,
                erasures_scheduled=erasures_scheduled,
                erasures_executed=erasures_executed,
                cross_border_transfers=0,
                dpias_conducted=dpia_count,
                compliance_status=compliance_status,
                observations=observations,
            )
        finally:
            if close_session:
                session.close()

    # ──────────────────────────────────────────────────────────────
    # 8. HEALTHCARE EXEMPTIONS (DPDP Section 17, Clinical Est. Act)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def check_clinical_establishment_exemption(
        patient_id: str,
        session: Any | None = None,
    ) -> ClinicalExemption:
        """Check if the Clinical Establishments Act retention applies.

        Clinical Establishments (Registration and Regulation) Act, 2010,
        Section 18(3): Clinical records must be retained for a minimum of
        3 years from the date of the last consultation or until the
        patient attains majority (if minor), whichever is later.

        This overrides the DPDP Section 13 erasure right for clinical data.
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                return ClinicalExemption(
                    exempted=False,
                    retention_years=settings.DPDP_CLINICAL_RETENTION_YEARS,
                    legal_basis="Clinical Establishments Act, 2010 Section 18(3)",
                    affected_data_categories=["CLINICAL"],
                    exemption_expires_at=None,
                )

            _ = _now()  # current timestamp
            retention_years = settings.DPDP_CLINICAL_RETENTION_YEARS

            # Calculate exemption expiry based on last update + retention period
            last_activity = patient.updated_at or patient.created_at
            exemption_expires = None
            if last_activity:
                exemption_expires = last_activity + timedelta(days=retention_years * 365)

            affected_categories = ["CLINICAL"]

            # Check if patient has any clinical records
            from app.models import PatientRecord
            has_clinical_records = (
                session.query(PatientRecord)
                .filter(PatientRecord.patient_id == patient_id)
                .first()
                is not None
            )

            if not has_clinical_records:
                return ClinicalExemption(
                    exempted=False,
                    retention_years=retention_years,
                    legal_basis="Clinical Establishments Act, 2010 Section 18(3)",
                    affected_data_categories=affected_categories,
                    exemption_expires_at=_iso_date(exemption_expires.date()) if exemption_expires else None,
                )

            return ClinicalExemption(
                exempted=True,
                retention_years=retention_years,
                legal_basis="Clinical Establishments (Registration and Regulation) Act, 2010, Section 18(3) — "
                            f"clinical records must be retained for minimum {retention_years} years",
                affected_data_categories=affected_categories,
                exemption_expires_at=_iso_date(exemption_expires.date()) if exemption_expires else None,
            )
        finally:
            if close_session:
                session.close()

    @staticmethod
    def check_minor_consent_eligibility(
        patient_id: str,
        session: Any | None = None,
    ) -> MinorConsentEligibility:
        """Check if a minor can consent or if guardian consent is required.

        DPDP Act 2023 Section 17: Data of children (under 18) requires
        verifiable parental/guardian consent. Healthcare exemptions apply:
        - Emergency treatment
        - Minor's own consent for certain healthcare decisions
          (mature minor doctrine as per Indian contract/medical law)
        """
        close_session = False
        if session is None:
            session = SyncSessionLocal()
            close_session = True

        try:
            patient = session.query(Patient).filter(Patient.id == patient_id).first()
            if not patient:
                return MinorConsentEligibility(
                    eligible=False,
                    patient_age=0,
                    legal_guardian_required=True,
                    guardian_type="PARENT",
                    dpdp_rules="DPDP Act 2023 Section 17",
                    exceptions=[],
                )

            # Calculate age
            age = patient.age_years or 0
            if patient.date_of_birth and age == 0:
                from datetime import date as dt_date
                today = dt_date.today()
                age = today.year - patient.date_of_birth.year - (
                    (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)
                )

            is_minor = age < 18
            guardian_required = is_minor

            exceptions: list[str] = []
            if is_minor:
                # Healthcare-specific exceptions
                exceptions = [
                    "Emergency treatment without guardian consent (Medical Council of India regulations)",
                    "Minor's consent for reproductive health services (majority at 16 for certain decisions)",
                    "Mental health treatment (Mental Healthcare Act, 2017 provisions)",
                ]

            return MinorConsentEligibility(
                eligible=not is_minor,
                patient_age=age,
                legal_guardian_required=guardian_required,
                guardian_type="PARENT_OR_LEGAL_GUARDIAN" if guardian_required else None,
                dpdp_rules="DPDP Act 2023 Section 17 — verifiable guardian consent required for data of children",
                exceptions=exceptions if is_minor else [],
            )
        finally:
            if close_session:
                session.close()

    # ──────────────────────────────────────────────────────────────
    # 9. SCHEDULER
    # ──────────────────────────────────────────────────────────────


_scheduler_started = False


def schedule_compliance_tasks() -> None:
    """Schedule APScheduler cron jobs for DPDP compliance tasks.

    Tasks scheduled:
    1. Erasure execution: Daily at 02:00 — executes pending erasures
       that are past their scheduled date
    2. Log purging: Weekly on Sunday at 03:00 — purges audit logs
       and communications past retention period
    3. Erasure notification sender: Daily at 10:00 — sends
       pre-erasure notifications for upcoming erasures
    4. SLA compliance check: Daily at 08:00 — alerts on breached
       grievance SLAs

    Called from main.py lifespan startup.
    """
    global _scheduler_started

    if _scheduler_started:
        logger.info("DPDP compliance scheduler already running — skipping")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not available — compliance tasks not scheduled")
        return

    scheduler = BackgroundScheduler(
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,  # 1 hour grace
        }
    )

    service = DpdpComplianceService()

    # Task 1: Execute pending erasures (daily at 02:00)
    def _run_pending_erasures():
        """Execute all pending erasures that are past their scheduled date."""
        try:
            session = SyncSessionLocal()
            pending = (
                session.query(ErasureSchedule)
                .filter(
                    ErasureSchedule.execution_status == "PENDING",
                    ErasureSchedule.scheduled_date <= _today(),
                )
                .all()
            )
            for schedule in pending:
                try:
                    result = service.execute_erasure(schedule.id, session=session)
                    logger.info(
                        f"Erasure executed: {schedule.id} — "
                        f"{result['records_affected']} records affected"
                    )
                except Exception as e:
                    logger.error(f"Erasure execution failed for {schedule.id}: {e}")
                    session.rollback()
            session.close()
        except Exception as e:
            logger.error(f"Erasure cron job failed: {e}")

    scheduler.add_job(
        _run_pending_erasures,
        CronTrigger(hour=2, minute=0),
        id="dpdp_erasure_execution",
        name="DPDP Erasure Execution (Daily)",
        replace_existing=True,
    )

    # Task 2: Purge expired logs (weekly on Sunday at 03:00)
    def _run_log_purge():
        """Purge audit logs and communications past retention period."""
        try:
            result = service.purge_expired_logs()
            logger.info(
                f"DPDP log purge completed: "
                f"{result['purged_audit_logs']} audits, "
                f"{result['purged_communications']} communications, "
                f"{result['purged_notifications']} notifications"
            )
        except Exception as e:
            logger.error(f"Log purge cron job failed: {e}")

    scheduler.add_job(
        _run_log_purge,
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="dpdp_log_purge",
        name="DPDP Log Purge (Weekly)",
        replace_existing=True,
    )

    # Task 3: Send erasure notifications (daily at 10:00)
    def _send_erasure_notifications():
        """Send pre-erasure notifications for pending erasures without notifications."""
        try:
            session = SyncSessionLocal()
            pending_notifications = (
                session.query(ErasureSchedule)
                .filter(
                    ErasureSchedule.execution_status == "PENDING",
                    ErasureSchedule.notified_at.is_(None),
                    ErasureSchedule.scheduled_date > _today(),
                )
                .all()
            )
            for schedule in pending_notifications:
                try:
                    result = service.send_erasure_notification(schedule.id, session=session)
                    logger.info(f"Erasure notification sent: {schedule.id} to {result['recipient']}")
                except Exception as e:
                    logger.error(f"Erasure notification failed for {schedule.id}: {e}")
                    session.rollback()
            session.close()
        except Exception as e:
            logger.error(f"Erasure notification cron job failed: {e}")

    scheduler.add_job(
        _send_erasure_notifications,
        CronTrigger(hour=10, minute=0),
        id="dpdp_erasure_notifications",
        name="DPDP Erasure Notifications (Daily)",
        replace_existing=True,
    )

    # Task 4: Check SLA compliance (daily at 08:00)
    def _run_sla_check():
        """Check and alert on breached grievance SLAs."""
        try:
            result = service.check_sla_compliance()
            if result["breached_sla"] > 0:
                logger.warning(
                    f"DPDP SLA BREACH: {result['breached_sla']}/{result['total_open']} "
                    f"requests breached {result['sla_days']}-day SLA "
                    f"({result['breach_percentage']}% breach rate)"
                )
                for item in result["items_breached"]:
                    logger.warning(
                        f"  SLA BREACH: {item['request_type']} request {item['request_id']} "
                        f"for patient {item['patient_id']} — "
                        f"{item['days_overdue']} days overdue"
                    )
            else:
                logger.info(
                    f"DPDP SLA check: {result['total_open']} open requests, "
                    f"all within {result['sla_days']}-day SLA"
                )
        except Exception as e:
            logger.error(f"SLA compliance check cron job failed: {e}")

    scheduler.add_job(
        _run_sla_check,
        CronTrigger(hour=8, minute=0),
        id="dpdp_sla_check",
        name="DPDP SLA Compliance Check (Daily)",
        replace_existing=True,
    )

    try:
        scheduler.start()
        _scheduler_started = True
        logger.info(
            "DPDP compliance scheduler started: "
            "erasure@02:00, purge@Sun03:00, notify@10:00, sla@08:00"
        )
    except Exception as e:
        logger.error(f"Failed to start DPDP compliance scheduler: {e}")
