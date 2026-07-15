"""HealthBridge Platform — SQLAlchemy Models"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional

# UTC now factory for SQLAlchemy default — evaluated per-row, not at import
def utcnow() -> datetime:
    return datetime.now(timezone.utc)

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, Date,
    Enum, ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, backref

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════

class ConsentStatus(str, PyEnum):
    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"
    REVOKED = "REVOKED"

class Gender(str, PyEnum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"

class RecordSourceType(str, PyEnum):
    HIE = "HIE"
    EHR = "EHR"
    LAB = "LAB"
    IMAGING = "IMAGING"
    PHARMACY = "PHARMACY"
    INSURANCE = "INSURANCE"
    PATIENT_PORTAL = "PATIENT_PORTAL"

class RecordType(str, PyEnum):
    CONDITION = "CONDITION"
    MEDICATION_REQUEST = "MEDICATION_REQUEST"
    MEDICATION_STATEMENT = "MEDICATION_STATEMENT"
    OBSERVATION = "OBSERVATION"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    PROCEDURE = "PROCEDURE"
    ENCOUNTER = "ENCOUNTER"
    ALLERGY_INTOLERANCE = "ALLERGY_INTOLERANCE"
    IMMUNIZATION = "IMMUNIZATION"
    DOCUMENT_REFERENCE = "DOCUMENT_REFERENCE"


class VitalSignType(str, PyEnum):
    """Standard vital sign types with LOINC codes for FHIR mapping."""
    SYSTOLIC_BP = "SYSTOLIC_BP"           # 8480-6
    DIASTOLIC_BP = "DIASTOLIC_BP"         # 8462-4
    HEART_RATE = "HEART_RATE"             # 8867-4
    RESPIRATORY_RATE = "RESPIRATORY_RATE" # 9279-1
    TEMPERATURE = "TEMPERATURE"           # 8310-5
    SPO2 = "SPO2"                         # 2708-6
    RBS = "RBS"                           # 14769-7 (Random Blood Sugar)
    WEIGHT = "WEIGHT"                     # 29463-7
    HEIGHT = "HEIGHT"                     # 8302-2
    BMI = "BMI"                           # 39156-5

class AuditAction(str, PyEnum):
    PATIENT_ACCESSED = "PATIENT_ACCESSED"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    DATA_INGESTED = "DATA_INGESTED"
    DATA_EXPORTED = "DATA_EXPORTED"
    DPDP_ACCESS_REQUEST = "DPDP_ACCESS_REQUEST"
    DPDP_CORRECTION_REQUEST = "DPDP_CORRECTION_REQUEST"
    DPDP_ERASURE_REQUEST = "DPDP_ERASURE_REQUEST"
    DPDP_GRIEVANCE_FILED = "DPDP_GRIEVANCE_FILED"
    BREACH_DETECTED = "BREACH_DETECTED"
    BREACH_NOTIFIED = "BREACH_NOTIFIED"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    USER_CREATED = "USER_CREATED"
    USER_LOCKED = "USER_LOCKED"

class BreachSeverity(str, PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class BreachStatus(str, PyEnum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    CONTAINED = "CONTAINED"
    RESOLVED = "RESOLVED"
    REPORTED_TO_BOARD = "REPORTED_TO_BOARD"

class UserRole(str, PyEnum):
    SUPER_ADMIN = "SUPER_ADMIN"       # Platform-wide admin
    ORG_ADMIN = "ORG_ADMIN"           # Clinic/hospital admin
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"
    COORDINATOR = "COORDINATOR"
    READ_ONLY = "READ_ONLY"

class SubscriptionTier(str, PyEnum):
    FREE = "FREE"
    STARTER = "STARTER"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"

class ConsentPurpose(str, PyEnum):
    TREATMENT = "TREATMENT"
    PAYMENT = "PAYMENT"
    OPERATIONS = "OPERATIONS"
    RESEARCH = "RESEARCH"
    PUBLIC_HEALTH = "PUBLIC_HEALTH"


# ═══════════════════════════════════════════════════
# Organization (Tenant)
# ═══════════════════════════════════════════════════

class Organization(Base):
    """A healthcare organization (clinic, hospital, practice) — the SaaS tenant."""

    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(128), unique=True, nullable=False, index=True)
    address = Column(Text, nullable=True)
    phone = Column(String(32), nullable=True)
    email = Column(String(255), nullable=True)
    registration_number = Column(String(128), nullable=True)  # Clinic registration / NABH
    subscription_tier = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE)
    subscription_starts_at = Column(DateTime, nullable=True)
    subscription_ends_at = Column(DateTime, nullable=True)
    max_staff = Column(Integer, default=5)
    max_patients = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    onboarding_completed = Column(Boolean, default=False)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    staff = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="organization", cascade="all, delete-orphan")


# ═══════════════════════════════════════════════════
# User & Auth
# ═══════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.READ_ONLY)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    is_locked = Column(Boolean, default=False)
    login_attempts = Column(Integer, default=0)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    organization = relationship("Organization", back_populates="staff")
    audit_logs = relationship("AuditLog", back_populates="user")


# ═══════════════════════════════════════════════════
# Patient
# ═══════════════════════════════════════════════════

class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        Index("ix_patient_mrn", "mrn"),
        Index("ix_patient_abha", "abha_number"),
        Index("ix_patient_tenant", "tenant_id"),
        UniqueConstraint("tenant_id", "mrn", name="uq_tenant_mrn"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    mrn = Column(String(64), nullable=False, index=True)
    uhid = Column(String(64), nullable=True, unique=True, index=True)  # Unique Health ID
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(Enum(Gender), default=Gender.UNKNOWN)
    phone = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    abha_number = Column(String(64), nullable=True, unique=True)
    aadhaar_hash = Column(String(128), nullable=True)
    consent_status = Column(Enum(ConsentStatus), default=ConsentStatus.PENDING)
    consent_id = Column(String(64), nullable=True)
    consent_manager_id = Column(String(64), nullable=True)
    consent_purposes = Column(JSON, default=list)
    consent_granted_at = Column(DateTime, nullable=True)
    consent_expires_at = Column(DateTime, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    blood_group = Column(String(8), nullable=True)
    emergency_contact_name = Column(Text, nullable=True)
    emergency_contact_phone = Column(Text, nullable=True)
    age_years = Column(Integer, nullable=True)
    city = Column(String(128), nullable=True)
    state = Column(String(128), nullable=True)
    pincode = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    created_by = Column(String(36), nullable=True)
    data_retention_until = Column(Date, nullable=True)

    organization = relationship("Organization", back_populates="patients")
    accounts = relationship("PatientAccountLink", back_populates="patient", cascade="all, delete-orphan")
    records = relationship("PatientRecord", back_populates="patient", cascade="all, delete-orphan")
    consents = relationship("ConsentRecord", back_populates="patient", cascade="all, delete-orphan")
    breach_notifications = relationship("BreachNotification", back_populates="patient")
    communications = relationship("CommunicationLog", back_populates="patient")
    vital_signs = relationship("VitalSign", back_populates="patient", cascade="all, delete-orphan")
    opd_registrations = relationship("OPDRegistration", back_populates="patient", cascade="all, delete-orphan")
    soap_notes = relationship("SOAPNote", back_populates="patient", cascade="all, delete-orphan")


class VitalSign(Base):
    """Vital Signs — structured observation entries for FHIR R4 Observation mapping."""
    __tablename__ = "vital_signs"
    __table_args__ = (
        Index("ix_vitals_patient_type", "patient_id", "vital_type"),
        Index("ix_vitals_recorded", "recorded_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    vital_type = Column(Enum(VitalSignType), nullable=False)
    value = Column(Text, nullable=False)  # Stored as string for flexibility (e.g., "120/80" for BP)
    value_numeric = Column(Text, nullable=True)  # Numeric value for charting/queries
    unit = Column(String(32), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    recorded_by = Column(String(36), nullable=True)  # User ID
    device_name = Column(String(128), nullable=True)
    device_serial = Column(String(128), nullable=True)
    method = Column(String(64), nullable=True)  # Manual, Automated, Calculated
    position = Column(String(32), nullable=True)  # sitting, standing, supine
    notes = Column(Text, nullable=True)
    is_abnormal = Column(Boolean, default=False)
    reference_range_low = Column(Text, nullable=True)
    reference_range_high = Column(Text, nullable=True)
    encounter_id = Column(String(36), nullable=True)  # Link to encounter if applicable
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="vital_signs")

    # FHIR Observation mapping helpers
    LOINC_CODES = {
        VitalSignType.SYSTOLIC_BP: "8480-6",
        VitalSignType.DIASTOLIC_BP: "8462-4",
        VitalSignType.HEART_RATE: "8867-4",
        VitalSignType.RESPIRATORY_RATE: "9279-1",
        VitalSignType.TEMPERATURE: "8310-5",
        VitalSignType.SPO2: "2708-6",
        VitalSignType.RBS: "14769-7",
        VitalSignType.WEIGHT: "29463-7",
        VitalSignType.HEIGHT: "8302-2",
        VitalSignType.BMI: "39156-5",
    }

    UNITS = {
        VitalSignType.SYSTOLIC_BP: "mmHg",
        VitalSignType.DIASTOLIC_BP: "mmHg",
        VitalSignType.HEART_RATE: "/min",
        VitalSignType.RESPIRATORY_RATE: "/min",
        VitalSignType.TEMPERATURE: "°C",
        VitalSignType.SPO2: "%",
        VitalSignType.RBS: "mg/dL",
        VitalSignType.WEIGHT: "kg",
        VitalSignType.HEIGHT: "cm",
        VitalSignType.BMI: "kg/m2",
    }

    @classmethod
    def get_loinc_code(cls, vital_type: VitalSignType) -> str:
        return cls.LOINC_CODES.get(vital_type, "")

    @classmethod
    def get_unit(cls, vital_type: VitalSignType) -> str:
        return cls.UNITS.get(vital_type, "")

    def to_fhir_observation(self) -> dict:
        """Convert to FHIR R4 Observation resource."""
        loinc = self.get_loinc_code(self.vital_type)
        unit = self.get_unit(self.vital_type)
        try:
            value_num = float(self.value_numeric) if self.value_numeric else float(self.value.split("/")[0] if "/" in self.value else self.value)
        except (ValueError, TypeError):
            value_num = None

        return {
            "resourceType": "Observation",
            "id": self.id,
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "vital-signs",
                    "display": "Vital Signs"
                }]
            }],
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": loinc,
                    "display": self.vital_type.value.replace("_", " ").title()
                }],
                "text": self.vital_type.value.replace("_", " ").title()
            },
            "subject": {"reference": f"Patient/{self.patient_id}"},
            "effectiveDateTime": self.recorded_at.isoformat() if self.recorded_at else None,
            "valueQuantity": {
                "value": value_num,
                "unit": unit,
                "system": "http://unitsofmeasure.org",
                "code": unit.replace("°C", "Cel").replace("%", "percent").replace("/min", "/min")
            } if value_num is not None else None,
            "valueString": self.value if value_num is None else None,
            "interpretation": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                    "code": "A" if self.is_abnormal else "N",
                    "display": "Abnormal" if self.is_abnormal else "Normal"
                }]
            }] if self.is_abnormal or self.reference_range_low or self.reference_range_high else None,
            "referenceRange": [{
                "low": {"value": float(self.reference_range_low), "unit": unit, "system": "http://unitsofmeasure.org"} if self.reference_range_low else None,
                "high": {"value": float(self.reference_range_high), "unit": unit, "system": "http://unitsofmeasure.org"} if self.reference_range_high else None,
            }] if self.reference_range_low or self.reference_range_high else None,
            "device": {"display": self.device_name} if self.device_name else None,
            "note": [{"text": self.notes}] if self.notes else None,
        }


# ═══════════════════════════════════════════════════
# OPD Registration & Token Queue
# ═══════════════════════════════════════════════════

class TokenStatus(str, PyEnum):
    WAITING = "WAITING"
    CALLED = "CALLED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    SKIPPED = "SKIPPED"
    NO_SHOW = "NO_SHOW"


class OPDRegistration(Base):
    """OPD Registration with UHID generation and token assignment."""
    __tablename__ = "opd_registrations"
    __table_args__ = (
        Index("ix_opd_uhid", "uhid", unique=True),
        Index("ix_opd_tenant_date", "tenant_id", "registration_date"),
        Index("ix_opd_patient", "patient_id"),
        Index("ix_opd_phone", "phone"),
        UniqueConstraint("tenant_id", "token_number", "registration_date", name="uq_tenant_token_date"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True)

    # UHID: UHID-YYYYMMDD-XXXX (unique per org per day)
    uhid = Column(String(32), nullable=False, unique=True, index=True)

    # Patient Demographics (denormalized for quick access at front desk)
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(Enum(Gender), default=Gender.UNKNOWN)
    phone = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    emergency_contact_name = Column(Text, nullable=True)
    emergency_contact_phone = Column(Text, nullable=True)

    # Registration metadata
    registration_date = Column(Date, default=datetime.utcnow, nullable=False, index=True)
    token_number = Column(Integer, nullable=False)  # Sequential per day per org
    estimated_wait_minutes = Column(Integer, default=0)

    # Status tracking
    status = Column(Enum(TokenStatus), default=TokenStatus.WAITING, nullable=False)
    chief_complaint = Column(Text, nullable=True)

    # Timestamps
    registered_at = Column(DateTime, default=datetime.utcnow)
    called_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Audit
    registered_by = Column(String(36), nullable=True)  # User ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    patient = relationship("Patient", back_populates="opd_registrations")
    tokens = relationship("TokenQueue", back_populates="registration", cascade="all, delete-orphan")


class TokenQueue(Base):
    """Token Queue for real-time doctor queue management."""
    __tablename__ = "token_queue"
    __table_args__ = (
        Index("ix_token_queue_status", "status"),
        Index("ix_token_queue_doctor", "doctor_id"),
        Index("ix_token_queue_tenant_date", "tenant_id", "queue_date"),
        Index("ix_token_queue_uhid", "uhid"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    registration_id = Column(String(36), ForeignKey("opd_registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    uhid = Column(String(32), nullable=False, index=True)

    token_number = Column(Integer, nullable=False, index=True)
    queue_date = Column(Date, default=datetime.utcnow, nullable=False, index=True)

    status = Column(Enum(TokenStatus), default=TokenStatus.WAITING, nullable=False, index=True)
    doctor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    room = Column(String(32), nullable=True)

    # Chief complaint for doctor's quick view
    chief_complaint = Column(Text, nullable=True)

    # Timestamps
    called_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    registration = relationship("OPDRegistration", back_populates="tokens")
    doctor = relationship("User", foreign_keys=[doctor_id])


# Update Patient model to add opd_registrations relationship
# Add this to Patient class: opd_registrations = relationship("OPDRegistration", back_populates="patient", cascade="all, delete-orphan")


# ═══════════════════════════════════════════════════
# SOAP Clinical Notes
# ═══════════════════════════════════════════════════


class SOAPNote(Base):
    """SOAP Clinical Note — Subjective, Objective, Assessment, Plan documentation."""

    __tablename__ = "soap_notes"
    __table_args__ = (
        Index("ix_soap_patient", "patient_id"),
        Index("ix_soap_encounter", "encounter_id"),
        Index("ix_soap_token", "token_id"),
        Index("ix_soap_created", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_id = Column(String(36), ForeignKey("opd_registrations.id", ondelete="CASCADE"), nullable=True, index=True)  # Links to OPDRegistration
    token_id = Column(String(36), ForeignKey("token_queue.id", ondelete="CASCADE"), nullable=True, index=True)  # Links to TokenQueue

    # SOAP Sections
    subjective = Column(Text, nullable=True)      # Patient's complaints, history, symptoms
    objective = Column(Text, nullable=True)       # Vitals, exam findings, observations
    assessment = Column(Text, nullable=True)      # Clinical impression, diagnosis
    plan = Column(Text, nullable=True)            # Treatment plan, medications, follow-up

    # Structured Clinical Data (for FHIR/Interop)
    chief_complaint = Column(Text, nullable=True)
    icd10_codes = Column(JSON, default=list)      # List of ICD-10 codes with descriptions
    snomed_codes = Column(JSON, default=list)     # List of SNOMED codes

    # Structured Plan Components
    medications = Column(JSON, default=list)      # Prescribed medications
    investigations = Column(JSON, default=list)   # Ordered investigations
    referrals = Column(JSON, default=list)        # Specialist referrals
    follow_up_date = Column(Date, nullable=True)
    follow_up_notes = Column(Text, nullable=True)

    # Versioning
    version = Column(Integer, default=1, nullable=False)
    parent_version_id = Column(String(36), ForeignKey("soap_notes.id", ondelete="SET NULL"), nullable=True)
    is_latest = Column(Boolean, default=True, nullable=False)

    # Status
    status = Column(String(32), default="DRAFT", nullable=False)  # DRAFT, FINAL, AMENDED
    completed_at = Column(DateTime, nullable=True)

    # Audit
    created_by = Column(String(36), nullable=True)  # User ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    patient = relationship("Patient", back_populates="soap_notes")
    versions = relationship("SOAPNote", backref=backref("parent_version", remote_side=[id]))


class PatientSOAPVersion(Base):
    """Audit trail for SOAP note versions — every keystroke logged for DPDP compliance."""

    __tablename__ = "soap_note_versions"
    __table_args__ = (
        Index("ix_soap_version_note", "soap_note_id"),
        Index("ix_soap_version_created", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    soap_note_id = Column(String(36), ForeignKey("soap_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)

    # Full snapshot of the note at this version
    subjective = Column(Text, nullable=True)
    objective = Column(Text, nullable=True)
    assessment = Column(Text, nullable=True)
    plan = Column(Text, nullable=True)
    chief_complaint = Column(Text, nullable=True)
    icd10_codes = Column(JSON, default=list)
    snomed_codes = Column(JSON, default=list)
    medications = Column(JSON, default=list)
    investigations = Column(JSON, default=list)
    referrals = Column(JSON, default=list)
    follow_up_date = Column(Date, nullable=True)
    follow_up_notes = Column(Text, nullable=True)

    # Change metadata
    changed_by = Column(String(36), nullable=True)
    change_summary = Column(Text, nullable=True)  # e.g., "Auto-save", "Manual save", "Assessment updated"
    word_count = Column(Integer, default=0)
    time_spent_seconds = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)


class ICD10Code(Base):
    """ICD-10-CM codes for diagnosis coding — cached for offline search."""

    __tablename__ = "icd10_codes"
    __table_args__ = (
        Index("ix_icd10_code", "code"),
        Index("ix_icd10_description", "description"),
        Index("ix_icd10_category", "category"),
        Index("ix_icd10_tenant", "tenant_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(16), nullable=False, index=True)  # e.g., E11.9, I10
    description = Column(Text, nullable=False)
    category = Column(String(64), nullable=True)  # e.g., "Endocrine", "Circulatory"
    subcategory = Column(String(64), nullable=True)
    is_billable = Column(Boolean, default=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Add to Patient model: soap_notes = relationship("SOAPNote", back_populates="patient", cascade="all, delete-orphan")


class PatientAccountLink(Base):
    __tablename__ = "patient_account_links"
    __table_args__ = (UniqueConstraint("patient_id", "source_type", "external_id", name="uq_patient_source"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(Enum(RecordSourceType), nullable=False)
    external_id = Column(String(255), nullable=False)
    source_system = Column(String(128), nullable=False)
    is_verified = Column(Boolean, default=False)
    last_sync = Column(DateTime, nullable=True)
    real_time_connected = Column(Boolean, default=False)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)

    patient = relationship("Patient", back_populates="accounts")


# ═══════════════════════════════════════════════════
# Clinical Records
# ═══════════════════════════════════════════════════

class PatientRecord(Base):
    __tablename__ = "patient_records"
    __table_args__ = (
        Index("ix_record_patient_type", "patient_id", "record_type"),
        Index("ix_record_source", "source_system"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    record_type = Column(Enum(RecordType), nullable=False)
    source_system = Column(String(128), nullable=False)
    source_type = Column(Enum(RecordSourceType), nullable=False)
    source_record_id = Column(String(255), nullable=True)
    fhir_resource_type = Column(String(64), nullable=True)
    fhir_resource_json = Column(Text, nullable=True)
    clinical_summary = Column(Text, nullable=True)
    code = Column(String(64), nullable=True)
    code_system = Column(String(64), nullable=True)
    display_name = Column(String(255), nullable=True)
    recorded_date = Column(DateTime, nullable=True)
    encounter_date = Column(Date, nullable=True)
    effective_start = Column(DateTime, nullable=True)
    effective_end = Column(DateTime, nullable=True)
    provider_name = Column(String(255), nullable=True)
    facility_name = Column(String(255), nullable=True)
    consent_id_used = Column(String(64), nullable=True)
    ingested_at = Column(DateTime, default=utcnow)
    ingested_by = Column(String(36), nullable=True)
    is_active = Column(Boolean, default=True)

    patient = relationship("Patient", back_populates="records")


# ═══════════════════════════════════════════════════
# Consent Records
# ═══════════════════════════════════════════════════

class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    consent_id = Column(String(64), unique=True, nullable=False)
    consent_manager_id = Column(String(64), nullable=True)
    consent_artifact_json = Column(Text, nullable=True)
    purpose = Column(Enum(ConsentPurpose), nullable=False)
    data_categories = Column(JSON, default=list)
    duration_days = Column(Integer, nullable=True)
    status = Column(Enum(ConsentStatus), default=ConsentStatus.GRANTED)
    previous_status = Column(Enum(ConsentStatus), nullable=True)
    granted_at = Column(DateTime, default=utcnow)
    withdrawn_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    notice_provided = Column(Boolean, default=True)
    notice_language = Column(String(8), default="en")
    notice_text = Column(Text, nullable=True)
    withdrawal_mechanism = Column(Text, nullable=True)
    recorded_by = Column(String(36), nullable=True)
    recorded_at = Column(DateTime, default=utcnow)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    patient = relationship("Patient", back_populates="consents")


# ═══════════════════════════════════════════════════
# Data Breach
# ═══════════════════════════════════════════════════

class DataBreach(Base):
    __tablename__ = "data_breaches"

    id = Column(String(36), primary_key=True, default=_uuid)
    breach_id = Column(String(64), unique=True, nullable=False)
    description = Column(Text, nullable=False)
    breach_type = Column(String(128), nullable=True)
    severity = Column(Enum(BreachSeverity), default=BreachSeverity.MEDIUM)
    status = Column(Enum(BreachStatus), default=BreachStatus.DETECTED)
    detected_at = Column(DateTime, default=utcnow)
    occurred_at = Column(DateTime, nullable=True)
    contained_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    affected_patient_count = Column(Integer, default=0)
    affected_data_categories = Column(JSON, default=list)
    remediation_steps = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    board_notified = Column(Boolean, default=False)
    board_notified_at = Column(DateTime, nullable=True)
    board_report_submitted = Column(Boolean, default=False)
    users_notified = Column(Boolean, default=False)
    users_notified_at = Column(DateTime, nullable=True)
    investigator_notes = Column(Text, nullable=True)
    findings_json = Column(JSON, default=dict)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class BreachNotification(Base):
    __tablename__ = "breach_notifications"

    id = Column(String(36), primary_key=True, default=_uuid)
    breach_id = Column(String(36), ForeignKey("data_breaches.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    channel = Column(String(32), nullable=False)
    recipient = Column(String(255), nullable=False)
    sent_at = Column(DateTime, default=utcnow)
    delivered = Column(Boolean, default=False)
    delivery_status = Column(String(64), nullable=True)
    breach_description = Column(Text, nullable=False)
    breach_timing = Column(Text, nullable=True)
    likely_consequences = Column(Text, nullable=True)
    mitigation_measures = Column(Text, nullable=True)
    safety_steps = Column(Text, nullable=True)
    contact_info = Column(String(255), nullable=True)

    patient = relationship("Patient", back_populates="breach_notifications")


# ═══════════════════════════════════════════════════
# Data Principal Requests
# ═══════════════════════════════════════════════════

class DataPrincipalRequest(Base):
    __tablename__ = "data_principal_requests"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    request_type = Column(String(32), nullable=False)
    request_details = Column(JSON, default=dict)
    status = Column(String(32), default="PENDING")
    rejection_reason = Column(Text, nullable=True)
    filed_at = Column(DateTime, default=utcnow)
    sla_deadline = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    response_data = Column(JSON, default=dict)
    response_notes = Column(Text, nullable=True)
    verified_by = Column(String(36), nullable=True)
    verification_method = Column(String(64), nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ═══════════════════════════════════════════════════
# Audit Logs
# ═══════════════════════════════════════════════════

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_timestamp", "timestamp"),
        Index("ix_audit_patient", "patient_id"),
        Index("ix_audit_action", "action"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    timestamp = Column(DateTime, default=utcnow, nullable=False, index=True)
    action = Column(Enum(AuditAction), nullable=False)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True)
    resource_id = Column(String(64), nullable=True)
    resource_type = Column(String(64), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    details_json = Column(JSON, default=dict)
    consent_id = Column(String(64), nullable=True)
    retention_until = Column(Date, nullable=True)

    user = relationship("User", back_populates="audit_logs")


# ═══════════════════════════════════════════════════
# Erasure Schedule
# ═══════════════════════════════════════════════════

class ErasureSchedule(Base):
    __tablename__ = "erasure_schedules"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    erasure_type = Column(String(16), default="FULL")
    erasure_reason = Column(String(32), nullable=False)
    scheduled_date = Column(Date, nullable=False)
    notified_at = Column(DateTime, nullable=True)
    notification_channel = Column(String(32), nullable=True)
    user_responded = Column(Boolean, default=False)
    user_response = Column(String(255), nullable=True)
    executed_at = Column(DateTime, nullable=True)
    executed_by = Column(String(36), nullable=True)
    execution_status = Column(String(32), default="PENDING")
    records_affected = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)


# ═══════════════════════════════════════════════════
# Communication Log
# ═══════════════════════════════════════════════════

class CommunicationLog(Base):
    __tablename__ = "communication_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(32), nullable=False)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    body_preview = Column(Text, nullable=True)
    purpose = Column(String(64), nullable=True)
    sent_at = Column(DateTime, default=utcnow)
    delivered = Column(Boolean, default=False)
    delivery_status = Column(String(64), nullable=True)
    read_at = Column(DateTime, nullable=True)
    template_used = Column(String(64), nullable=True)

    patient = relationship("Patient", back_populates="communications")


# ═══════════════════════════════════════════════════
# ABHA Transactions
# ═══════════════════════════════════════════════════

class ABHATransaction(Base):
    __tablename__ = "abha_transactions"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=True, index=True)
    transaction_type = Column(String(32), nullable=False)
    abha_address = Column(String(128), nullable=True)
    transaction_id = Column(String(128), nullable=True)
    request_payload = Column(JSON, default=dict)
    response_status = Column(Integer, nullable=True)
    response_body = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    user_id = Column(String(36), nullable=True)
    ip_address = Column(String(45), nullable=True)


# ═══════════════════════════════════════════════════
# Conversion Logs
# ═══════════════════════════════════════════════════

class ConversionLog(Base):
    __tablename__ = "conversion_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), nullable=True, index=True)
    source_format = Column(String(16), nullable=False)
    target_format = Column(String(16), nullable=False)
    success = Column(Boolean, default=False)
    source_size_bytes = Column(Integer, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    resources_converted = Column(Integer, nullable=True)
    validation_errors = Column(Integer, default=0)
    validation_warnings = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    fhir_version = Column(String(8), default="R4")
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=utcnow)


# ═══════════════════════════════════════════════════
# Document Ingestion Logs
# ═══════════════════════════════════════════════════

class IngestionLog(Base):
    """Tracks every document ingested via photo/scan → OCR → AI extraction."""

    __tablename__ = "ingestion_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True)
    document_type = Column(String(32), nullable=False)  # prescription, lab_report, pharmacy_bill, discharge_summary
    source_format = Column(String(8), default="photo")  # photo, pdf, scan
    original_filename = Column(String(255), nullable=True)
    file_path = Column(String(512), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    ocr_text = Column(Text, nullable=True)
    extracted_json = Column(JSON, default=dict)
    confidence_score = Column(Integer, nullable=True)  # 0-100
    fhir_resource_type = Column(String(64), nullable=True)
    fhir_resource_id = Column(String(64), nullable=True)
    status = Column(String(16), default="PENDING")  # PENDING, PROCESSED, FAILED
    error_message = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=utcnow)


# ═══════════════════════════════════════════════════
# WhatsApp Message Logs
# ═══════════════════════════════════════════════════

class WhatsAppMessageLog(Base):
    """Tracks WhatsApp messages processed through the ingestion webhook."""

    __tablename__ = "whatsapp_message_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    provider = Column(String(16), nullable=False)  # meta, twilio
    sender = Column(String(32), nullable=False, index=True)
    message_id = Column(String(128), nullable=True)
    media_type = Column(String(16), nullable=True)  # image, document, text
    original_filename = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    caption = Column(Text, nullable=True)
    text_body = Column(Text, nullable=True)
    document_type = Column(String(32), nullable=True)
    ingestion_status = Column(String(16), nullable=True)
    ingestion_log_id = Column(String(36), nullable=True)
    confidence_score = Column(Integer, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    reply_sent = Column(Boolean, default=False)
    reply_text = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    raw_payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)


# ═══════════════════════════════════════════════════
# OPD Token Queue
# ═══════════════════════════════════════════════════

class VisitType(str, PyEnum):
    NEW = "NEW"
    FOLLOWUP = "FOLLOWUP"
    EMERGENCY = "EMERGENCY"
    REFERRAL = "REFERRAL"

class TokenStatus(str, PyEnum):
    WAITING = "WAITING"
    CALLED = "CALLED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"

class OPDTokenQueue(Base):
    __tablename__ = "opd_token_queue"
    
    id = Column(String(36), primary_key=True, default=_uuid)
    token_number = Column(Integer, nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    visit_type = Column(Enum(VisitType), default=VisitType.NEW)
    status = Column(Enum(TokenStatus), default=TokenStatus.WAITING, index=True)
    queue_position = Column(Integer, default=0)
    estimated_wait_minutes = Column(Integer, default=0)
    called_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    doctor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    
    patient = relationship("Patient")
    doctor = relationship("User")
    tenant = relationship("Organization")
    
    __table_args__ = (
        UniqueConstraint("tenant_id", "token_number", "created_at", name="uq_tenant_token_date"),
        Index("ix_opd_queue_tenant_status", "tenant_id", "status"),
    )