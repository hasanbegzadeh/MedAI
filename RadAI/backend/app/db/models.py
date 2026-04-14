"""RadAI — SQLAlchemy async ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, Integer,
    SmallInteger, String, Text, ForeignKey, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="resident")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    findings_reviewed = relationship("Finding", back_populates="reviewer", foreign_keys="Finding.reviewed_by")
    reports_signed = relationship("Report", back_populates="signer")
    audit_entries = relationship("AuditLog", back_populates="user")


class Study(Base):
    __tablename__ = "studies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    orthanc_id = Column(String(64), unique=True, nullable=False)
    study_instance_uid = Column(String(128), unique=True, nullable=False)
    accession_number = Column(String(64))
    modality = Column(String(16), nullable=False)
    body_part = Column(String(64))
    study_description = Column(String(255))
    anonymized_uid = Column(String(128))
    num_series = Column(Integer, default=0)
    num_instances = Column(Integer, default=0)
    ai_status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    ai_jobs = relationship("AIJob", back_populates="study", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="study", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="study", cascade="all, delete-orphan")
    audit_entries = relationship("AuditLog", back_populates="study")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String(128), nullable=False)
    version = Column(String(64), nullable=False)
    hash = Column(String(128))
    config_json = Column(JSONB)
    status = Column(String(32), nullable=False, default="testing")  # active/deprecated/testing/retired
    deployed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    metrics = relationship("ModelMetric", back_populates="model_version", cascade="all, delete-orphan")
    ai_jobs = relationship("AIJob", back_populates="model_version")

    __table_args__ = (
        # Unique constraint on (model_name, version)
        {"sqlite_autoincrement": False},
    )


class ModelMetric(Base):
    __tablename__ = "model_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)
    metric_name = Column(String(64), nullable=False)
    metric_value = Column(Float, nullable=False)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id"), nullable=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    model_version = relationship("ModelVersion", back_populates="metrics")


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String(64), nullable=False)
    celery_task_id = Column(String(128))
    status = Column(String(32), nullable=False, default="queued")
    tier = Column(SmallInteger, nullable=False, default=1)
    model_name = Column(String(128))
    model_version_id = Column(UUID(as_uuid=True), ForeignKey("model_versions.id"), nullable=True)
    progress_pct = Column(SmallInteger, default=0)
    error_message = Column(Text)
    result_json = Column(JSONB)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    study = relationship("Study", back_populates="ai_jobs")
    model_version = relationship("ModelVersion", back_populates="ai_jobs")
    findings = relationship("Finding", back_populates="ai_job")


class Finding(Base):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    ai_job_id = Column(UUID(as_uuid=True), ForeignKey("ai_jobs.id"))
    finding_type = Column(String(64), nullable=False)
    location = Column(String(128))
    laterality = Column(String(16))
    segmentation_id = Column(String(128))
    series_instance_uid = Column(String(128))
    sop_instance_uid = Column(String(128))
    slice_index = Column(Integer)
    measurements = Column(JSONB)                    # {longest_diameter_mm, volume_mm3, mean_hu}
    characteristics = Column(ARRAY(Text))           # ["solid", "spiculated"]
    confidence = Column(Float)                      # 0.0-1.0
    lung_rads_category = Column(String(16))
    li_rads_category = Column(String(16))
    status = Column(String(32), nullable=False, default="pending")
    radiologist_notes = Column(Text)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    study = relationship("Study", back_populates="findings")
    ai_job = relationship("AIJob", back_populates="findings")
    reviewer = relationship("User", back_populates="findings_reviewed", foreign_keys=[reviewed_by])


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(String(32), nullable=False, default="draft")
    template_name = Column(String(64))
    content_text = Column(Text)
    content_html = Column(Text)
    dicom_sr_uid = Column(String(128))
    classification = Column(String(32))
    ai_polished = Column(Boolean, default=False)
    ai_model_used = Column(String(128))
    extracted_keywords = Column(JSONB)
    signed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    signed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    study = relationship("Study", back_populates="reports")
    signer = relationship("User", back_populates="reports_signed")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id"))
    action = Column(String(64), nullable=False)
    entity_type = Column(String(32))
    entity_id = Column(UUID(as_uuid=True))
    detail = Column(JSONB)
    ip_address = Column(INET)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="audit_entries")
    study = relationship("Study", back_populates="audit_entries")
