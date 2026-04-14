"""RadAI — Multi-modality support registry.

Defines supported imaging modalities, their AI models, report templates,
and DICOM processing requirements.

Supported Modalities:
- CT (Computed Tomography): TotalSegmentator, nodule detection
- MRI (Magnetic Resonance Imaging): Brain, spine, MSK segmentation
- X-ray (Radiography): CheXpert pathology detection
- Ultrasound: Basic measurements, fetal biometry (future)
- Mammography: BI-RADS assessment (future)

Usage::

    registry = ModalityRegistry()
    modality = registry.get_modability("MR")  # DICOM modality code
    models = modality.get_available_models()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class ModalityType(str, Enum):
    CT = "CT"
    MR = "MR"  # MRI
    CR = "CR"  # Computed Radiography (X-ray)
    DX = "DX"  # Digital Radiography (X-ray)
    US = "US"  # Ultrasound
    MG = "MG"  # Mammography
    PT = "PT"  # PET
    NM = "NM"  # Nuclear Medicine


@dataclass
class ModalityConfig:
    """Configuration for a supported imaging modality."""
    name: str
    dicom_codes: list[str]  # DICOM Modality type codes
    body_parts: list[str]  # Supported anatomical regions
    ai_models: dict[str, dict]  # Available AI models and their configs
    report_templates: dict[str, str]  # Template name -> filename
    processing_requirements: dict[str, Any]  # Special processing needs
    tier: int  # Priority: 1=primary, 2=secondary, 3=future


# ─── Modality Definitions ────────────────────────────────────────────────────

MODALITY_REGISTRY: dict[str, ModalityConfig] = {
    "CT": ModalityConfig(
        name="Computed Tomography",
        dicom_codes=["CT"],
        body_parts=["chest", "abdomen", "pelvis", "head", "neck", "spine", "extremities"],
        ai_models={
            "totalsegmentator": {
                "description": "117 anatomical structure segmentation",
                "vram_gb": 3.0,
                "tier": 1,  # Local
                "cloud_tier": 3,  # Full-res cloud option
            },
            "nodule_detection": {
                "description": "Lung nodule candidate detection",
                "vram_gb": 0.0,  # Runs on CPU after segmentation
                "tier": 1,
            },
            "nninteractive": {
                "description": "Interactive segmentation refinement",
                "vram_gb": 6.0,
                "tier": 1,
            },
            "litemedsam": {
                "description": "Fast SAM-based segmentation fallback",
                "vram_gb": 2.5,
                "tier": 1,
            },
        },
        report_templates={
            "lung_rads": "lung_rads.j2",
            "general_ct": "general_ct.j2",
            "ct_angio": "ct_angio.j2",
        },
        processing_requirements={
            "conversion": "DICOM → NIfTI",
            "windowing": "CT HU values (-1000 to +3000)",
            "anisotropy": "Often anisotropic (slice thickness 1-5mm)",
        },
        tier=1,
    ),

    "MRI": ModalityConfig(
        name="Magnetic Resonance Imaging",
        dicom_codes=["MR"],
        body_parts=["brain", "spine", "knee", "shoulder", "hip", "abdomen", "pelvis", "heart"],
        ai_models={
            "nnunet_brain": {
                "description": "Brain structure segmentation (hippocampus, ventricles, lesions)",
                "vram_gb": 4.0,
                "tier": 1,
                "status": "planned",
            },
            "spine_segmentation": {
                "description": "Intervertebral disc and vertebral body segmentation",
                "vram_gb": 3.0,
                "tier": 1,
                "status": "planned",
            },
            "litemedsam": {
                "description": "Fast SAM-based segmentation fallback",
                "vram_gb": 2.5,
                "tier": 1,
            },
        },
        report_templates={
            "brain_mri": "brain_mri.j2",
            "spine_mri": "spine_mri.j2",
            "msk_mri": "msk_mri.j2",
            "general_mri": "general_mri.j2",
        },
        processing_requirements={
            "conversion": "DICOM → NIfTI (multi-echo support)",
            "windowing": "MRI intensity (no standard scale, relative values)",
            "multi_series": "Often multiple sequences (T1, T2, FLAIR, DWI)",
        },
        tier=2,
    ),

    "XRAY": ModalityConfig(
        name="Digital Radiography (X-ray)",
        dicom_codes=["CR", "DX"],
        body_parts=["chest", "abdomen", "pelvis", "hand", "foot", "spine", "skull"],
        ai_models={
            "chexpert": {
                "description": "14 pathology classification (CheXpert)",
                "vram_gb": 2.0,
                "tier": 1,
                "pathologies": [
                    "Atelectasis", "Cardiomegaly", "Consolidation", "Edema",
                    "Pleural Effusion", "Pneumothorax", "Pneumonia",
                    "Fracture", "Nodule", "Mass",
                ],
            },
            "litemedsam": {
                "description": "Fast SAM-based segmentation fallback",
                "vram_gb": 2.5,
                "tier": 1,
            },
        },
        report_templates={
            "chest_xray": "chest_xray.j2",
            "bone_xray": "bone_xray.j2",
            "general_xray": "general_xray.j2",
        },
        processing_requirements={
            "conversion": "DICOM → PNG/HDF5 (2D projection)",
            "windowing": "Wide dynamic range, auto-windowing recommended",
            "resolution": "High spatial resolution (2K-4K pixels)",
        },
        tier=2,
    ),

    "US": ModalityConfig(
        name="Ultrasound",
        dicom_codes=["US"],
        body_parts=["abdomen", "pelvis", "thyroid", "breast", "heart", "fetal", "vascular"],
        ai_models={
            "fetal_biometry": {
                "description": "Automated fetal measurements (BPD, HC, AC, FL)",
                "vram_gb": 2.0,
                "tier": 1,
                "status": "planned",
            },
            "thyroid_nodules": {
                "description": "Thyroid nodule detection and TI-RADS scoring",
                "vram_gb": 2.5,
                "tier": 1,
                "status": "planned",
            },
        },
        report_templates={
            "general_us": "general_us.j2",
            "obstetric_us": "obstetric_us.j2",
            "thyroid_us": "thyroid_us.j2",
        },
        processing_requirements={
            "conversion": "DICOM → video/frames (cine loop support)",
            "windowing": "Log-compressed intensity, vendor-specific",
            "temporal": "Often includes cine clips (30+ frames)",
        },
        tier=3,  # Future
    ),

    "MG": ModalityConfig(
        name="Mammography",
        dicom_codes=["MG"],
        body_parts=["breast"],
        ai_models={
            "breast_density": {
                "description": "BI-RADS breast density assessment",
                "vram_gb": 2.0,
                "tier": 1,
                "status": "planned",
            },
            "mass_detection": {
                "description": "Breast mass/calcification detection",
                "vram_gb": 3.0,
                "tier": 1,
                "status": "planned",
            },
        },
        report_templates={
            "bi_rads": "bi_rads.j2",
        },
        processing_requirements={
            "conversion": "DICOM → high-bit-depth PNG (12-16 bit)",
            "windowing": "Full dynamic range display",
            "views": "CC and MLO views required for assessment",
        },
        tier=3,  # Future
    ),
}


class ModalityError(Exception):
    """Raised when modality operations fail."""


class ModalityRegistry:
    """Registry and factory for multi-modality imaging support."""

    def __init__(self) -> None:
        self._registry = MODALITY_REGISTRY

    def get_modality(self, dicom_code: str) -> ModalityConfig:
        """Get modality config by DICOM Modality type.

        Args:
            dicom_code: DICOM Modality code (e.g., "CT", "MR", "DX").

        Returns:
            ModalityConfig for the modality.

        Raises:
            ModalityError: If modality not supported.
        """
        # Direct lookup
        if dicom_code.upper() in self._registry:
            return self._registry[dicom_code.upper()]

        # Map X-ray variants
        if dicom_code.upper() in ("CR", "DX"):
            return self._registry["XRAY"]

        raise ModalityError(f"Unsupported modality: {dicom_code}")

    def get_supported_modalities(self) -> list[str]:
        """Return list of supported modality names."""
        return list(self._registry.keys())

    def get_available_models(self, dicom_code: str) -> list[dict[str, Any]]:
        """Return available AI models for the modality.

        Args:
            dicom_code: DICOM Modality type.

        Returns:
            List of model info dicts with name, description, VRAM, tier.
        """
        modality = self.get_modality(dicom_code)
        models = []
        for name, config in modality.ai_models.items():
            models.append({
                "name": name,
                "description": config.get("description", ""),
                "vram_gb": config.get("vram_gb", 0),
                "tier": config.get("tier", 1),
                "status": config.get("status", "available"),
            })
        return models

    def get_report_templates(self, dicom_code: str) -> dict[str, str]:
        """Return available report templates for the modality.

        Args:
            dicom_code: DICOM Modality type.

        Returns:
            Dict mapping template name to filename.
        """
        modality = self.get_modality(dicom_code)
        return modality.report_templates

    def is_supported(self, dicom_code: str) -> bool:
        """Check if modality is supported."""
        try:
            self.get_modality(dicom_code)
            return True
        except ModalityError:
            return False

    def recommend_template(
        self, dicom_code: str, body_part: str | None = None
    ) -> str:
        """Recommend the best report template for the study.

        Args:
            dicom_code: DICOM Modality type.
            body_part: Anatomical region.

        Returns:
            Recommended template name.
        """
        modality = self.get_modality(dicom_code)
        templates = modality.report_templates

        # Body-part specific recommendations
        if body_part:
            bp_lower = body_part.lower()
            if "chest" in bp_lower and "chest_xray" in templates:
                return "chest_xray"
            if "brain" in bp_lower and "brain_mri" in templates:
                return "brain_mri"
            if "spine" in bp_lower and "spine_mri" in templates:
                return "spine_mri"
            if "breast" in bp_lower and "bi_rads" in templates:
                return "bi_rads"
            if "thyroid" in bp_lower and "thyroid_us" in templates:
                return "thyroid_us"

        # Default to first template
        return next(iter(templates))


# ─── Singleton ────────────────────────────────────────────────────────────────
_registry: ModalityRegistry | None = None


def get_modality_registry() -> ModalityRegistry:
    """Return the process-wide ModalityRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ModalityRegistry()
    return _registry
