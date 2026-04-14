"""RadAI — DICOM Structured Report (SR) Generation.

Creates DICOM-SR (Structured Report) objects from radiology report text
using highdicom. SR objects can be stored in PACS alongside imaging studies.

Reference: DICOM PS3.3 — Structured Report (SR) IOD.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import pydicom
import structlog
from pydicom.sr.codedict import codes
from pydicom.uid import generate_uid

logger = structlog.get_logger(__name__)


class DicomSRError(Exception):
    """Raised when DICOM-SR creation fails."""


def create_dicom_sr_text(
    report_text: str,
    source_images: list[pydicom.Dataset],
    title: str = "Radiology Report",
    author: str | None = None,
    classification: str | None = None,
    template_name: str | None = None,
) -> pydicom.Dataset:
    """Create a DICOM Text SR from report text.

    Uses the Basic Text SR IOD which is simpler and more compatible
    than Comprehensive3DSR. Content is stored as TEXT content items
    in a hierarchical tree.

    Args:
        report_text: Full report text.
        source_images: Source DICOM datasets (for evidence).
        title: Report title.
        author: Interpreting radiologist name.
        classification: e.g., "Lung-RADS 3".
        template_name: Template used.

    Returns:
        pydicom Dataset representing the DICOM-SR.
    """
    logger.info(
        "Creating DICOM-SR (Text SR)",
        title=title,
        author=author,
        num_source_images=len(source_images),
    )

    if not source_images:
        raise DicomSRError("At least one source image is required")

    ds = _build_text_sr(
        report_text, title, author, classification, template_name, source_images
    )

    logger.info("DICOM-SR created successfully")
    return ds


def _build_text_sr(
    report_text: str,
    title: str,
    author: str | None,
    classification: str | None,
    template_name: str | None,
    source_images: list[pydicom.Dataset],
) -> pydicom.Dataset:
    """Build a Basic Text SR dataset.

    Structure:
    └─ CONTAINER (Title)
       ├─ TEXT (Report content)
       ├─ TEXT (Classification)
       └─ PNAME (Author)
    """
    from pydicom.dataset import Dataset
    from pydicom.sequence import Sequence
    from pydicom.uid import ExplicitVRLittleEndian

    ds = Dataset()

    # SOP Class: Basic Text SR
    ds.SOPClassUID = pydicom.uid.BasicTextSRStorage
    ds.SOPInstanceUID = generate_uid()

    # Patient info (from first source image)
    ref = source_images[0]
    ds.PatientName = getattr(ref, "PatientName", "Anonymous")
    ds.PatientID = getattr(ref, "PatientID", "UNKNOWN")
    ds.PatientBirthDate = getattr(ref, "PatientBirthDate", "")
    ds.PatientSex = getattr(ref, "PatientSex", "")

    # Study info
    ds.StudyInstanceUID = getattr(ref, "StudyInstanceUID", generate_uid())
    ds.StudyID = getattr(ref, "StudyID", "1")
    ds.StudyDate = getattr(ref, "StudyDate", datetime.date.today().strftime("%Y%m%d"))
    ds.StudyTime = getattr(ref, "StudyTime", "")
    ds.AccessionNumber = getattr(ref, "AccessionNumber", "")
    ds.ReferringPhysicianName = getattr(ref, "ReferringPhysicianName", "")

    # Series
    ds.Modality = "SR"
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = 900
    ds.SeriesDescription = f"RadAI Report: {title}"
    ds.SeriesDate = ds.StudyDate
    ds.SeriesTime = ds.StudyTime

    # Instance
    ds.InstanceNumber = 1
    ds.ContentDate = ds.StudyDate
    ds.ContentTime = ds.StudyTime
    ds.InstitutionName = getattr(ref, "InstitutionName", "RadAI Medical Center")
    ds.Manufacturer = "RadAI"
    ds.ManufacturerModelName = "RadAI Reporting Pipeline v0.1"
    ds.SoftwareVersions = "0.1.0"

    # SR Document
    ds.SpecificCharacterSet = "ISO_IR 100"
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = Sequence([
        _code_item("121058", "DCM", "Title of this document")
    ])
    ds.ContinuityOfContent = "SEPARATE"

    # Content sequence: report text + classification
    content_seq = Sequence()

    # Report text
    text_item = Dataset()
    text_item.RelationshipType = "CONTAINS"
    text_item.ValueType = "TEXT"
    text_item.ConceptNameCodeSequence = Sequence([
        _code_item("121071", "DCM", "Findings")
    ])
    text_item.TextValue = report_text
    content_seq.append(text_item)

    # Classification
    if classification:
        class_item = Dataset()
        class_item.RelationshipType = "CONTAINS"
        class_item.ValueType = "TEXT"
        class_item.ConceptNameCodeSequence = Sequence([
            _code_item("121070", "DCM", "Conclusion")
        ])
        class_item.TextValue = classification
        content_seq.append(class_item)

    # Author
    if author:
        author_item = Dataset()
        author_item.RelationshipType = "CONTAINS"
        author_item.ValueType = "PNAME"
        author_item.ConceptNameCodeSequence = Sequence([
            _code_item("121007", "DCM", "Person Observer Name")
        ])
        author_item.PersonName = author
        content_seq.append(author_item)

    # Template
    if template_name:
        template_item = Dataset()
        template_item.RelationshipType = "CONTAINS"
        template_item.ValueType = "TEXT"
        template_item.ConceptNameCodeSequence = Sequence([
            _code_item("121072", "DCM", "Template identifier")
        ])
        template_item.TextValue = template_name
        content_seq.append(template_item)

    ds.ContentSequence = content_seq

    # Referenced images
    ref_seq = Sequence()
    for img in source_images:
        ref_item = Dataset()
        ref_item.RelationshipType = "SELECTED FROM"
        ref_item.ReferencedSOPClassUID = img.SOPClassUID
        ref_item.ReferencedSOPInstanceUID = img.SOPInstanceUID
        ref_seq.append(ref_item)

    # Add referenced images to content
    ref_container = Dataset()
    ref_container.RelationshipType = "CONTAINS"
    ref_container.ValueType = "CONTAINER"
    ref_container.ConceptNameCodeSequence = Sequence([
        _code_item("121112", "DCM", "Source of Evidence")
    ])
    ref_container.ContentSequence = ref_seq
    content_seq.append(ref_container)

    # Transfer syntax
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.file_meta = Dataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID

    return ds


def _code_item(value: str, scheme: str, meaning: str) -> pydicom.Dataset:
    """Create a Code Sequence item."""
    item = pydicom.Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = scheme
    item.CodeMeaning = meaning
    return item


def save_dicom_sr(sr: pydicom.Dataset, output_path: str | Path) -> Path:
    """Save a DICOM-SR to file.

    Args:
        sr: pydicom Dataset (SR).
        output_path: Destination .dcm path.

    Returns:
        Path to the written file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure file_meta is set
    if not hasattr(sr, "file_meta") or sr.file_meta is None:
        from pydicom.uid import ExplicitVRLittleEndian
        sr.file_meta = pydicom.Dataset()
        sr.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        sr.file_meta.MediaStorageSOPClassUID = getattr(sr, "SOPClassUID", pydicom.uid.BasicTextSRStorage)
        sr.file_meta.MediaStorageSOPInstanceUID = getattr(sr, "SOPInstanceUID", generate_uid())

    sr.save_as(str(output_path), write_like_original=False)
    logger.info("DICOM-SR saved", path=str(output_path))
    return output_path
