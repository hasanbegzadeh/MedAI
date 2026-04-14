"""RadAI — AI Pipeline Orchestrator."""

import shutil
from pathlib import Path
from uuid import UUID
from typing import Callable, Any, Awaitable

import numpy as np
import structlog
import SimpleITK as sitk
from app.config import Settings
from app.services.pacs_service import PACSService
from app.services.findings_service import FindingsService
from app.dicom.converter import dicom_series_to_nifti

logger = structlog.get_logger(__name__)


class AIPipeline:
    """Orchestrates the multi-step AI inference pipeline."""

    def __init__(
        self,
        study_id: UUID,
        job_id: UUID,
        settings: Settings,
        pacs: PACSService,
        findings: FindingsService,
        progress_callback: Callable[[int], Awaitable[None]],
    ):
        self.study_id = study_id
        self.job_id = job_id
        self.settings = settings
        self.pacs = pacs
        self.findings = findings
        self.progress_callback = progress_callback
        
        self.temp_dir = Path(settings.temp_processing_dir) / f"{study_id}_{job_id}"
        self.dicom_dir = self.temp_dir / "dicom"
        self.nifti_path = self.temp_dir / "volume.nii.gz"
        self.output_dir = self.temp_dir / "output"

    async def initialize(self):
        """Prepare temporary working directory."""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.dicom_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def cleanup(self):
        """Remove temporary working directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info("Pipeline temp directory cleaned up", path=str(self.temp_dir))

    async def run_step(self, name: str, progress: int, func: Callable, *args, **kwargs):
        """Execute a single pipeline step with logging and progress updates."""
        logger.info("Executing pipeline step", step=name, job_id=str(self.job_id))
        await self.progress_callback(progress)
        
        if hasattr(func, "__name__") and func.__name__ == "AsyncClient":
             # Handle async functions if needed
             pass

        result = await func(*args, **kwargs)
        logger.info("Step completed", step=name)
        return result

    async def fetch_data(self, orthanc_study_id: str):
        """Step: Download DICOM data from PACS."""
        series_ids = await self.pacs.get_study_series(orthanc_study_id)
        if not series_ids:
            raise ValueError("No series found in study")
        
        # In this simplified refactor, we just take the first series
        await self.pacs.download_series_to_dir(series_ids[0], self.dicom_dir)

    async def convert_to_nifti(self):
        """Step: Convert DICOM series to NIfTI."""
        dicom_series_to_nifti(self.dicom_dir, self.nifti_path)

    async def persist_results(self, candidates: list):
        """Step: Persist findings to database."""
        await self.findings.persist_nodule_findings(
            self.study_id, self.job_id, candidates
        )
        await self.findings.update_job_status(
            self.job_id, status="completed", progress_pct=100
        )

    async def detect_nodules_in_volume(self, lung_mask_dir: Path) -> list:
        """Step: Process lung masks and run nodule detection."""
        ct_image = sitk.ReadImage(str(self.nifti_path))
        ct_volume = sitk.GetArrayFromImage(ct_image)
        spacing = ct_image.GetSpacing()
        spacing_mm = (spacing[2], spacing[1], spacing[0])

        mask_files = list(lung_mask_dir.glob("*.nii.gz"))
        if not mask_files:
            raise ValueError("No lung masks found")

        lung_mask = np.zeros(ct_volume.shape, dtype=np.int32)
        label = 1
        for mf in mask_files:
            mask_img = sitk.ReadImage(str(mf))
            mask_arr = sitk.GetArrayFromImage(mask_img)
            lung_mask[mask_arr > 0] = label
            label += 1

        from app.ai.nodule_detection import detect_nodules
        return detect_nodules(ct_volume, lung_mask, spacing_mm)
