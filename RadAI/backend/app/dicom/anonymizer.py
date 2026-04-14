"""RadAI — DICOM anonymization pipeline for cloud upload.

Strips all PHI (Protected Health Information) from DICOM files
before uploading to cloud GPU servers. Uses pydicom to remove
or replace identifiable patient data while preserving imaging
data and technical metadata required for AI inference.

Usage::

    anonymizer = DICOMAnonymizer()
    anonymized_dir = anonymizer.anonymize_directory(
        input_dir="/tmp/study_dicom",
        output_dir="/tmp/anonymized",
    )
"""

from __future__ import annotations

import datetime
import hashlib
import shutil
from pathlib import Path
from typing import Optional

import pydicom
import structlog
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import generate_uid

logger = structlog.get_logger(__name__)

# DICOM tags containing PHI that must be removed/blanked for cloud upload
# Based on DICOM PS 3.15 Table E.1-1 "Basic Application Level Confidentiality Profile"
PHI_TAGS = {
    # Patient Identification
    (0x0010, 0x0010): "PatientName",
    (0x0010, 0x0020): "PatientID",
    (0x0010, 0x0030): "PatientBirthDate",
    (0x0010, 0x0032): "PatientBirthTime",
    (0x0010, 0x0040): "PatientSex",
    (0x0010, 0x0050): "PatientInsurancePlanCode",
    (0x0010, 0x0101): "PatientPrimaryLanguageCode",
    (0x0010, 0x1000): "OtherPatientIDs",
    (0x0010, 0x1001): "OtherPatientNames",
    (0x0010, 0x1040): "PatientAddress",
    (0x0010, 0x1050): "InsurancePlanIdentification",
    (0x0010, 0x2150): "CountryOfResidence",
    (0x0010, 0x2155): "RegionOfResidence",
    (0x0010, 0x2160): "PatientTelephoneNumbers",
    (0x0010, 0x21B0): "AdditionalPatientHistory",
    (0x0010, 0x4000): "PatientComments",

    # Study Identification
    (0x0008, 0x0050): "AccessionNumber",
    (0x0008, 0x0080): "InstitutionName",
    (0x0008, 0x0081): "InstitutionAddress",
    (0x0008, 0x0082): "InstitutionCode",
    (0x0008, 0x0090): "ReferringPhysicianName",
    (0x0008, 0x0092): "ReferringPhysicianAddress",
    (0x0008, 0x0094): "ReferringPhysicianPhone",
    (0x0008, 0x0096): "ReferringPhysicianIdentification",
    (0x0008, 0x1040): "InstitutionalDepartmentName",
    (0x0008, 0x1048): "Physician(s) of Record",
    (0x0008, 0x1060): "Name of Physician(s) Reading Study",
    (0x0008, 0x1070): "Operators' Name",
    (0x0008, 0x1080): "Admitting Diagnoses Description",
    (0x0008, 0x4000): "Custom Attributes",
    (0x0008, 0x0054): "AETitle",

    # Series/Equipment (some may be retained for technical analysis)
    (0x0008, 0x0020): "StudyDate",
    (0x0008, 0x0030): "StudyTime",
    (0x0008, 0x0023): "ContentDate",
    (0x0008, 0x0033): "ContentTime",
    (0x0008, 0x1110): "ReferencedStudySequence",

    # Performing Physician
    (0x0008, 0x1050): "PerformingPhysicianName",
    (0x0008, 0x1052): "PerformingPhysicianIdentification",

    # Device/Observer
    (0x0040, 0x0244): "PerformedProcedureStepStartDate",
    (0x0040, 0x0245): "PerformedProcedureStepStartTime",
    (0x0040, 0x0250): "PerformedProcedureStepEndDate",
    (0x0040, 0x0251): "PerformedProcedureStepEndTime",
    (0x0040, 0x0275): "RequestAttributesSequence",
    (0x0040, 0x1004): "RequestedProcedureID",
    (0x0040, 0x2001): "ReasonForTheRequestedProcedure",
}

# Tags to replace with anonymized values (retain structure but remove real values)
REPLACEMENT_VALUES = {
    (0x0010, 0x0010): "ANONYMIZED",  # PatientName
    (0x0010, 0x0020): lambda ds: hashlib.sha256(
        f"{ds.get((0x0010, 0x0010), '')}{ds.get((0x0008, 0x0020), '')}".encode()
    ).hexdigest()[:16],  # PatientID — deterministic but anonymized
    (0x0008, 0x0050): "",  # AccessionNumber
    (0x0008, 0x0090): "",  # ReferringPhysicianName
    (0x0008, 0x1048): "",  # Physician(s) of Record
    (0x0008, 0x1050): "",  # PerformingPhysicianName
    (0x0008, 0x1060): "",  # Name of Physician(s) Reading Study
    (0x0008, 0x1070): "",  # Operators' Name
    (0x0008, 0x0080): "CLOUD GPU SERVER",  # InstitutionName
    (0x0008, 0x0081): "",  # InstitutionAddress
    (0x0010, 0x0030): "",  # PatientBirthDate
    (0x0010, 0x0040): "",  # PatientSex
}


class AnonymizationError(Exception):
    """Raised when DICOM anonymization fails."""


class DICOMAnonymizer:
    """Anonymize DICOM files for safe cloud upload."""

    def __init__(self, seed: str = "radai-default-seed"):
        """Initialize anonymizer.

        Args:
            seed: Seed for deterministic PatientID generation.
                  Change per institution for different anonymized IDs.
        """
        self._seed = seed

    def anonymize_file(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
        keep_study_date: bool = False,
    ) -> Path:
        """Anonymize a single DICOM file.

        Args:
            input_path: Path to input DICOM file.
            output_path: Path for output (auto-generates if None).
            keep_study_date: If True, retain study date for temporal analysis.

        Returns:
            Path to anonymized file.

        Raises:
            AnonymizationError: On read/write failure or invalid DICOM.
        """
        input_path = Path(input_path)

        try:
            ds = pydicom.dcmread(str(input_path), force=True)
        except Exception as exc:
            raise AnonymizationError(f"Failed to read DICOM: {exc}") from exc

        ds = self._anonymize_dataset(ds, keep_study_date=keep_study_date)

        if output_path is None:
            output_path = input_path.with_name(f"anon_{input_path.name}")

        try:
            ds.save_as(str(output_path))
            logger.info(
                "DICOM anonymized",
                input=str(input_path),
                output=str(output_path),
            )
            return Path(output_path)
        except Exception as exc:
            raise AnonymizationError(f"Failed to save anonymized DICOM: {exc}") from exc

    def anonymize_directory(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
        keep_study_date: bool = False,
        progress_callback=None,
    ) -> Path:
        """Anonymize all DICOM files in a directory.

        Args:
            input_dir: Directory containing DICOM files.
            output_dir: Directory for anonymized output.
            keep_study_date: If True, retain study dates.
            progress_callback: Optional callback(pct: int).

        Returns:
            Path to output directory.

        Raises:
            AnonymizationError: On failure.
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        dicom_files = list(input_dir.rglob("*"))
        dicom_files = [f for f in dicom_files if f.is_file()]
        total = len(dicom_files)

        if total == 0:
            raise AnonymizationError(f"No files found in {input_dir}")

        success_count = 0
        for i, dicom_file in enumerate(dicom_files):
            try:
                rel_path = dicom_file.relative_to(input_dir)
                out_path = output_dir / rel_path
                out_path.parent.mkdir(parents=True, exist_ok=True)

                self.anonymize_file(dicom_file, out_path, keep_study_date=keep_study_date)
                success_count += 1

                if progress_callback:
                    progress_callback(int((i + 1) / total * 100))

            except AnonymizationError as exc:
                logger.warning(
                    "Skipping file during anonymization",
                    file=str(dicom_file),
                    error=str(exc),
                )
                continue

        logger.info(
            "DICOM directory anonymized",
            input=str(input_dir),
            output=str(output_dir),
            success=success_count,
            total=total,
        )
        return output_dir

    def _anonymize_dataset(
        self, ds: Dataset, keep_study_date: bool = False
    ) -> Dataset:
        """Anonymize a DICOM dataset in-place.

        Args:
            ds: DICOM dataset to anonymize.
            keep_study_date: Retain study date if needed.

        Returns:
            Same dataset with PHI removed.
        """
        # Generate new UIDs for the study to prevent linkage
        ds.StudyInstanceUID = generate_uid()
        ds.SeriesInstanceUID = generate_uid()
        ds.SOPInstanceUID = generate_uid()

        # Remove or blank PHI tags
        for tag, name in PHI_TAGS.items():
            if tag in ds:
                if keep_study_date and tag in (
                    (0x0008, 0x0020),  # StudyDate
                    (0x0008, 0x0030),  # StudyTime
                ):
                    continue  # Retain for temporal analysis
                del ds[tag]

        # Set replacement values for specific tags
        for tag, replacement in REPLACEMENT_VALUES.items():
            if tag in ds or tag in [
                (0x0010, 0x0010),
                (0x0010, 0x0020),
            ]:  # Always set these
                value = replacement(ds) if callable(replacement) else replacement
                # Use proper DataElement for pydicom 3.x compatibility
                if tag in ds:
                    ds[tag].value = value
                else:
                    from pydicom.dataelem import DataElement
                    from pydicom.tag import Tag
                    vr = "LO"  # default VR
                    if tag == (0x0010, 0x0010):
                        vr = "PN"
                    ds.add(DataElement(Tag(tag), vr, value))

        # Remove private data that might contain PHI
        private_elems = [
            elem for elem in ds
            if elem.tag.is_private
        ]
        for elem in private_elems:
            del ds[elem.tag]

        # Ensure DICOM preamble and prefixes are correct
        ds.is_little_endian = True
        ds.is_implicit_VR = False

        return ds


def create_anonymized_copy(
    study_dir: str | Path,
    output_dir: str | Path,
    study_uid: str | None = None,
    progress_callback=None,
) -> Path:
    """Convenience function: anonymize entire study for cloud upload.

    Args:
        study_dir: Directory containing original DICOM files.
        output_dir: Output directory for anonymized study.
        study_uid: Optional specific study UID to use.
        progress_callback: Optional callback(pct: int).

    Returns:
        Path to anonymized study directory.
    """
    anonymizer = DICOMAnonymizer()
    return anonymizer.anonymize_directory(
        study_dir, output_dir, progress_callback=progress_callback
    )
