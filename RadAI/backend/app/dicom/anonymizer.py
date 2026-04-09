"""RadAI — DICOM anonymization before cloud upload.

CRITICAL: Strip ALL patient-identifying tags before sending to cloud services.
This module must be called on every study before Tier 2/3 cloud processing.
"""
from __future__ import annotations

import copy
import uuid
from pathlib import Path

import pydicom
import structlog

logger = structlog.get_logger(__name__)

# DICOM tags that MUST be removed or replaced (HIPAA Safe Harbor PHI tags)
# Ref: DICOM PS 3.15 Table E.1-1 (Basic Application Level Confidentiality Profile)
_TAGS_TO_REMOVE = {
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientSex",
    "PatientAge",
    "PatientAddress",
    "PatientTelephoneNumbers",
    "PatientMotherBirthName",
    "PatientWeight",
    "PatientSize",
    "EthnicGroup",
    "OtherPatientIDs",
    "OtherPatientNames",
    "PatientComments",
    "ResponsiblePerson",
    "ResponsibleOrganization",
    "InstitutionName",
    "InstitutionAddress",
    "InstitutionalDepartmentName",
    "ReferringPhysicianName",
    "PhysiciansOfRecord",
    "PerformingPhysicianName",
    "NameOfPhysiciansReadingStudy",
    "RequestingPhysician",
    "OperatorsName",
    "StudyDate",
    "SeriesDate",
    "AcquisitionDate",
    "ContentDate",
    "StudyTime",
    "SeriesTime",
    "AcquisitionTime",
    "ContentTime",
    "AccessionNumber",
    "StudyID",
    "StationName",
    "DeviceSerialNumber",
    "SoftwareVersions",
    "ProtocolName",
    "RequestedProcedureDescription",
    "ScheduledProcedureStepDescription",
    "RequestAttributesSequence",
}

_SERIES_UID_PREFIX = "1.2.826.0.1.3680043.8.498.1"  # RadAI OID prefix


class AnonymizationError(Exception):
    """Raised when DICOM anonymization fails."""


def anonymize_dicom_file(
    input_path: str | Path,
    output_path: str | Path,
    study_uid_map: dict[str, str] | None = None,
) -> Path:
    """Anonymize a single DICOM file.

    Args:
        input_path: Source DICOM instance.
        output_path: Destination path for anonymized copy.
        study_uid_map: Optional mapping of original → replacement UIDs
                       (keeps consistency across series in same study).

    Returns:
        Path to the anonymized DICOM file.

    Raises:
        AnonymizationError: If the file cannot be read or written.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        ds = pydicom.dcmread(str(input_path))
    except Exception as exc:
        raise AnonymizationError(f"Cannot read DICOM file {input_path}: {exc}") from exc

    # Remove or blank PHI tags
    for tag_name in _TAGS_TO_REMOVE:
        if hasattr(ds, tag_name):
            try:
                delattr(ds, tag_name)
            except AttributeError:
                pass

    # Replace UIDs with deterministic but non-traceable values
    if study_uid_map is not None and ds.StudyInstanceUID in study_uid_map:
        ds.StudyInstanceUID = study_uid_map[ds.StudyInstanceUID]
    else:
        anon_uid = pydicom.uid.generate_uid(prefix=f"{_SERIES_UID_PREFIX}.")
        if study_uid_map is not None:
            study_uid_map.setdefault(ds.StudyInstanceUID, anon_uid)
        ds.StudyInstanceUID = anon_uid

    ds.PatientName = "RadAI^Anonymous"
    ds.PatientID = f"RADAI-{uuid.uuid4().hex[:8].upper()}"
    ds.file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID

    try:
        ds.save_as(str(output_path))
    except Exception as exc:
        raise AnonymizationError(f"Cannot write anonymized DICOM to {output_path}: {exc}") from exc

    return output_path


def anonymize_dicom_series(
    input_dir: str | Path,
    output_dir: str | Path,
) -> tuple[Path, dict[str, str]]:
    """Anonymize all DICOM files in a directory.

    Args:
        input_dir: Directory containing original DICOM files.
        output_dir: Directory to write anonymized files.

    Returns:
        (output_dir, uid_map) where uid_map maps original → anonymized UIDs.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    uid_map: dict[str, str] = {}
    files = list(input_dir.glob("*.dcm")) + list(input_dir.glob("IM*"))

    if not files:
        raise AnonymizationError(f"No DICOM files found in {input_dir}")

    logger.info("Anonymizing DICOM series", file_count=len(files), output=str(output_dir))

    for dcm_file in files:
        anon_name = f"{uuid.uuid4().hex}.dcm"
        anonymize_dicom_file(
            input_path=dcm_file,
            output_path=output_dir / anon_name,
            study_uid_map=uid_map,
        )

    logger.info("Anonymization complete", uid_map_size=len(uid_map))
    return output_dir, uid_map
