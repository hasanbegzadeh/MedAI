"""RadAI — Lung Nodule Detection from CT studies.

Heuristic-based nodule detection using TotalSegmentator lung ROI masks.
Works by:
1. Loading the CT volume and lung segmentation masks
2. Masking CT to lung regions only
3. Thresholding for tissue-density regions (-700 to +300 HU)
4. Connected component labelinging to find candidate nodules
5. Filtering by size (2-30mm equivalent diameter)
6. Measuring each candidate: volume, mean HU, diameter, location

This is a Phase 1 prototype. Production should use MONAI pretrained
lung nodule detection model (Plan 2+).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class NoduleCandidate:
    """A detected lung nodule candidate."""
    nodule_id: str
    location: str  # e.g. "Right Upper Lobe", "Left Lower Lobe"
    laterality: str  # "right" | "left" | "bilateral"
    lobe: str  # "upper" | "middle" | "lower"
    centroid: tuple[float, float, float]  # (x, y, z) in mm
    diameter_mm: float  # Equivalent spherical diameter
    volume_mm3: float
    mean_hu: float
    max_hu: float
    min_hu: float
    confidence: float  # 0.0-1.0 heuristic confidence
    slice_indices: List[int] = field(default_factory=list)


def detect_nodules(
    ct_volume: np.ndarray,
    lung_mask: np.ndarray,
    spacing_mm: tuple[float, float, float] = (1.0, 1.0, 1.0),
    lung_labels: Optional[dict[str, int]] = None,
) -> List[NoduleCandidate]:
    """Detect lung nodule candidates from a CT volume and lung mask.

    Args:
        ct_volume: 3D numpy array (Z, Y, X) in Hounsfield Units.
        lung_mask: 3D numpy array with lung segmentation labels.
            If dict labels, 1=left lung, 2=right lung.
            If binary, 1=all lung.
        spacing_mm: Voxel spacing in mm (z, y, x).
        lung_labels: Optional mapping of label name to int value.
            e.g. {"lung_left": 1, "lung_right": 2}

    Returns:
        List of NoduleCandidate objects.
    """
    from scipy import ndimage

    logger.info(
        "Starting nodule detection",
        ct_shape=ct_volume.shape,
        mask_shape=lung_mask.shape,
        spacing=spacing_mm,
    )

    if ct_volume.shape != lung_mask.shape:
        raise ValueError(
            f"CT volume shape {ct_volume.shape} != lung mask shape {lung_mask.shape}"
        )

    # Convert to float32 for HU operations
    ct = ct_volume.astype(np.float32)

    # Build left/right lung masks
    if lung_labels and len(set(lung_mask.flatten())) > 2:
        # Multi-label mask
        left_lung_mask = lung_mask == lung_labels.get("lung_left", 1)
        right_lung_mask = lung_mask == lung_labels.get("lung_right", 2)
    else:
        # Binary mask — split by midline (x-center)
        binary_mask = lung_mask > 0
        mid_x = binary_mask.shape[2] // 2
        left_lung_mask = binary_mask.copy()
        left_lung_mask[:, :, mid_x:] = False
        right_lung_mask = binary_mask.copy()
        right_lung_mask[:, :, :mid_x] = False

    # Detect nodules in each lung
    candidates: List[NoduleCandidate] = []
    nodule_counter = 0

    for side, mask in [("left", left_lung_mask), ("right", right_lung_mask)]:
        if not np.any(mask):
            continue

        side_candidates = _detect_in_lung(
            ct, mask, spacing_mm, side, nodule_counter
        )
        candidates.extend(side_candidates)
        nodule_counter += len(side_candidates)

    logger.info(
        "Nodule detection complete",
        total_candidates=len(candidates),
    )

    return candidates


def _detect_in_lung(
    ct: np.ndarray,
    lung_mask: np.ndarray,
    spacing: tuple[float, float, float],
    side: str,
    counter_start: int,
) -> List[NoduleCandidate]:
    """Detect nodules within a single lung mask.

    Strategy:
    1. Mask CT to lung region
    2. Threshold for tissue-density (-700 to +300 HU) — excludes air and bone
    3. Connected component labelinging
    4. Filter by size (2-30mm diameter)
    5. Measure each candidate
    """
    from scipy import ndimage

    # Mask CT to lung region
    lung_ct = np.where(lung_mask, ct, -1000).astype(np.float32)

    # Threshold for tissue-density regions
    # Nodules: -700 to +300 HU (excludes air at -1000, includes soft tissue ~40 HU)
    tissue_mask = (lung_ct > -700) & (lung_ct < 300)

    # Remove very large structures (consolidation, not nodules)
    # Keep only small connected components
    labeled, num_features = ndimage.label(tissue_mask)

    if num_features == 0:
        return []

    # Measure each component
    candidates = []
    voxel_volume_mm3 = spacing[0] * spacing[1] * spacing[2]
    nodule_counter = counter_start

    for label_id in range(1, num_features + 1):
        component_mask = labeled == label_id

        # Volume in voxels
        voxel_count = np.sum(component_mask)
        volume_mm3 = voxel_count * voxel_volume_mm3

        # Equivalent spherical diameter: d = 2 * (3V / 4pi)^(1/3)
        if volume_mm3 < 1:
            continue
        diameter_mm = 2 * ((3 * volume_mm3) / (4 * np.pi)) ** (1 / 3)

        # Filter: 2-30mm (clinical nodule range)
        if diameter_mm < 2 or diameter_mm > 30:
            continue

        # Get HU statistics
        hu_values = ct[component_mask]
        mean_hu = float(np.mean(hu_values))
        max_hu = float(np.max(hu_values))
        min_hu = float(np.min(hu_values))

        # Centroid in voxel coordinates
        centroid_voxel = ndimage.center_of_mass(component_mask)
        centroid_mm = (
            centroid_voxel[2] * spacing[2],  # x
            centroid_voxel[1] * spacing[1],  # y
            centroid_voxel[0] * spacing[0],  # z
        )

        # Determine lobe from z-position (crude approximation)
        z_normalized = centroid_voxel[0] / ct.shape[0]
        if z_normalized < 0.33:
            lobe = "upper"
        elif z_normalized < 0.66:
            lobe = "middle" if side == "right" else "lower"
        else:
            lobe = "lower"

        location = f"{side.capitalize()} {lobe.capitalize()} Lobe"

        # Confidence heuristic:
        # Higher for nodules near 0 HU (soft tissue), lower for very dense or very lucent
        if -200 <= mean_hu <= 100:
            confidence = 0.7
        elif -400 <= mean_hu <= 200:
            confidence = 0.5
        else:
            confidence = 0.3

        # Adjust for size: very small (<4mm) or large (>20mm) less confident
        if diameter_mm < 4:
            confidence *= 0.7
        elif diameter_mm > 20:
            confidence *= 0.6

        # Get slice indices
        slice_indices = list(np.unique(np.where(component_mask)[0]))

        nodule_counter += 1
        candidates.append(NoduleCandidate(
            nodule_id=f"NOD-{side[0].upper()}{nodule_counter:03d}",
            location=location,
            laterality=side,
            lobe=lobe,
            centroid=centroid_mm,
            diameter_mm=round(diameter_mm, 1),
            volume_mm3=round(volume_mm3, 1),
            mean_hu=round(mean_hu, 1),
            max_hu=round(max_hu, 1),
            min_hu=round(min_hu, 1),
            confidence=round(confidence, 2),
            slice_indices=slice_indices,
        ))

    return candidates


def run_nodule_detection_job(
    job_id,
    study_id,
    ct_nifti_path: str,
    lung_mask_path: str,
    spacing_mm: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict:
    """Run nodule detection as a background job.

    Args:
        job_id: AIJob UUID.
        study_id: Study UUID.
        ct_nifti_path: Path to CT NIfTI file.
        lung_mask_path: Path to lung segmentation NIfTI mask.
        spacing_mm: Voxel spacing.

    Returns:
        Dict with candidate list and metadata.
    """
    import SimpleITK as sitk

    logger.info(
        "Running nodule detection job",
        job_id=str(job_id),
        ct_path=ct_nifti_path,
        mask_path=lung_mask_path,
    )

    # Load CT volume
    ct_image = sitk.ReadImage(ct_nifti_path)
    ct_volume = sitk.GetArrayFromImage(ct_image)  # (Z, Y, X)

    # Load lung mask
    mask_image = sitk.ReadImage(lung_mask_path)
    lung_mask = sitk.GetArrayFromImage(mask_image)

    # Get actual spacing
    spacing = ct_image.GetSpacing()  # (x, y, z)
    spacing_mm = (spacing[2], spacing[1], spacing[0])  # Reorder to (z, y, x)

    # Detect nodules
    candidates = detect_nodules(ct_volume, lung_mask, spacing_mm)

    # Convert to serializable format
    results = {
        "total_candidates": len(candidates),
        "candidates": [
            {
                "nodule_id": c.nodule_id,
                "location": c.location,
                "laterality": c.laterality,
                "lobe": c.lobe,
                "centroid_mm": list(c.centroid),
                "diameter_mm": c.diameter_mm,
                "volume_mm3": c.volume_mm3,
                "mean_hu": c.mean_hu,
                "max_hu": c.max_hu,
                "min_hu": c.min_hu,
                "confidence": c.confidence,
                "slice_count": len(c.slice_indices),
            }
            for c in candidates
        ],
        "spacing_mm": list(spacing_mm),
    }

    logger.info(
        "Nodule detection job complete",
        candidates=len(candidates),
    )

    return results
