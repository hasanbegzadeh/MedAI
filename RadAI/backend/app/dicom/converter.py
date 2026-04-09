"""RadAI — DICOM ↔ NIfTI conversion utilities."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import SimpleITK as sitk
import structlog

logger = structlog.get_logger(__name__)


class DicomConverterError(Exception):
    """Raised when DICOM conversion fails."""


def dicom_series_to_nifti(
    dicom_dir: str | Path,
    output_path: str | Path | None = None,
    temp_dir: str = "/tmp/radai-processing",
) -> Path:
    """Convert a DICOM series directory to a NIfTI file.

    Args:
        dicom_dir: Directory containing DICOM files for a single series.
        output_path: Destination .nii.gz path. Auto-generated if None.
        temp_dir: Fallback temp directory if output_path not provided.

    Returns:
        Path to the created .nii.gz file.

    Raises:
        DicomConverterError: On any conversion failure.
    """
    dicom_dir = Path(dicom_dir)
    if not dicom_dir.is_dir():
        raise DicomConverterError(f"DICOM directory not found: {dicom_dir}")

    if output_path is None:
        os.makedirs(temp_dir, exist_ok=True)
        output_path = Path(temp_dir) / f"{uuid.uuid4()}.nii.gz"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Converting DICOM → NIfTI", src=str(dicom_dir), dst=str(output_path))

    try:
        reader = sitk.ImageSeriesReader()
        dicom_names = reader.GetGDCMSeriesFileNames(str(dicom_dir))
        if not dicom_names:
            raise DicomConverterError(f"No DICOM series found in: {dicom_dir}")
        reader.SetFileNames(dicom_names)
        image = reader.Execute()

        # Apply rescale slope/intercept (HU conversion)
        image = sitk.Cast(image, sitk.sitkFloat32)

        sitk.WriteImage(image, str(output_path))
        logger.info("NIfTI written", path=str(output_path), size_mb=output_path.stat().st_size / 1e6)
        return output_path

    except Exception as exc:
        raise DicomConverterError(f"SimpleITK conversion failed: {exc}") from exc


def nifti_to_dicom_seg(
    nifti_mask_path: str | Path,
    reference_dicom_dir: str | Path,
    output_path: str | Path,
    structure_name: str = "TotalSegmentator Structure",
    series_description: str = "RadAI Segmentation",
) -> Path:
    """Convert a NIfTI segmentation mask to DICOM-SEG format.

    Args:
        nifti_mask_path: Path to the .nii.gz segmentation mask.
        reference_dicom_dir: Original DICOM series (to pull metadata/geometry).
        output_path: Destination DICOM-SEG .dcm path.
        structure_name: Name of the segmented structure.
        series_description: Description for the new DICOM series.

    Returns:
        Path to the created DICOM-SEG file.
    """
    import pydicom
    from highdicom.seg.content import SegmentDescription
    from highdicom.seg.sop import Segmentation
    from pydicom.sr.codedict import codes
    from app.dicom.seg_export import get_segment_description

    nifti_mask_path = Path(nifti_mask_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Converting NIfTI → DICOM-SEG", nifti=str(nifti_mask_path), dst=str(output_path))

    try:
        # 1. Load source DICOM datasets (for metadata and spatial geometry)
        reader = sitk.ImageSeriesReader()
        dicom_files = reader.GetGDCMSeriesFileNames(str(reference_dicom_dir))
        source_datasets = [pydicom.dcmread(f) for f in dicom_files]
        
        # 2. Load the NIfTI mask image
        mask_image = sitk.ReadImage(str(nifti_mask_path))
        mask_array = sitk.GetArrayFromImage(mask_image)
        
        # 3. Create a segment description (SNOMED-CT based)
        segment_num = 1
        segment_description = get_segment_description(structure_name.lower(), segment_num)

        # 4. Create the Segmentation SOP Instance
        seg_instance = Segmentation(
            source_images=source_datasets,
            pixel_array=mask_array.astype(bool),
            segmentation_type="BINARY",
            segment_descriptions=[segment_description],
            series_description=series_description,
            series_number=500,  # Conventional start for segments
            sop_instance_uid=pydicom.uid.generate_uid(),
        )

        seg_instance.save_as(str(output_path))
        logger.info("DICOM-SEG written", path=str(output_path))
        return output_path

    except Exception as exc:
        logger.error(f"NIfTI → DICOM-SEG conversion failed: {exc}")
        raise DicomConverterError(f"Highdicom conversion failed: {exc}") from exc


def get_image_metadata(nifti_path: str | Path) -> dict:
    """Extract spacing, origin, size metadata from a NIfTI file."""
    image = sitk.ReadImage(str(nifti_path))
    return {
        "spacing_mm": list(image.GetSpacing()),
        "size_voxels": list(image.GetSize()),
        "origin": list(image.GetOrigin()),
        "direction": list(image.GetDirection()),
    }
