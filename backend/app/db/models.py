"""Database models.

The design simulates a small health-information exchange:
  * each Hospital keeps its own ClinicalRecords (the hospital that wrote a note owns it);
  * a Patient has one network-wide health ID and can be registered at several hospitals;
  * a Practitioner works at one hospital and, by default, sees only records written there;
  * records from other hospitals need patient Consent (simulated OTP) or an emergency
    "break-the-glass" grant, and every access is written to the AccessLog.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from backend.app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    city = Column(String(80), default="")


class Practitioner(Base):
    __tablename__ = "practitioners"

    id = Column(Integer, primary_key=True)
    username = Column(String(60), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    role = Column(String(60), default="Physician")
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    password_hash = Column(String(200), nullable=False)


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    health_id = Column(String(20), unique=True, nullable=False, index=True)  # network-wide ID (like ABHA)
    full_name = Column(String(120), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String(10), default="")
    blood_type = Column(String(5), default="")
    phone = Column(String(20), default="")
    emergency_contact = Column(String(160), default="")


class PatientRegistration(Base):
    """A patient is a registered patient of a hospital (that hospital's staff may see its records)."""
    __tablename__ = "patient_registrations"
    __table_args__ = (UniqueConstraint("patient_id", "hospital_id"),)

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    local_mrn = Column(String(30), default="")  # the hospital's own medical record number
    registered_at = Column(DateTime, default=utcnow, nullable=False)


class ClinicalRecord(Base):
    __tablename__ = "clinical_records"

    id = Column(Integer, primary_key=True, index=True)
    clinical_note = Column(Text, nullable=False)
    extracted_entities = Column(Text, nullable=False)
    api_results = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    # Patient context (nullable so stand-alone note analysis still works)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True)
    practitioner_id = Column(Integer, ForeignKey("practitioners.id"), nullable=True)
    visit_date = Column(Date, nullable=True)


class AccessGrant(Base):
    """Permission for a hospital to see a patient's records from OTHER hospitals."""
    __tablename__ = "access_grants"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    practitioner_id = Column(Integer, ForeignKey("practitioners.id"), nullable=False)
    kind = Column(String(20), nullable=False)  # "consent" | "emergency"
    reason = Column(Text, default="")
    granted_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)


class ConsentRequest(Base):
    """Simulated OTP sent to the patient's phone to approve sharing."""
    __tablename__ = "consent_requests"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    practitioner_id = Column(Integer, ForeignKey("practitioners.id"), nullable=False)
    code_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)


class AccessLog(Base):
    __tablename__ = "access_log"

    id = Column(Integer, primary_key=True)
    practitioner_id = Column(Integer, ForeignKey("practitioners.id"), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True)
    action = Column(String(40), nullable=False)
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow, nullable=False)
