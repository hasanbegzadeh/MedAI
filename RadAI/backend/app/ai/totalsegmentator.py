"""RadAI — TotalSegmentator integration."""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from uuid import UUID

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIJob, Study
from app.db.session import AsyncSessionLocal
from app.scheduler import get_scheduler, ModelSchedulerError
from app.websocket import manager
from app.dicom.converter import dicom_series_to_nifti, nifti_to_dicom_seg
from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


async def run_totalsegmentator_cloud_job(
    job_id: UUID, study_id: UUID, roi_subset: list[str] | None = None
):
    """Run TotalSegmentator on cloud GPU (Tier 3, full resolution).

    Anonymizes DICOM, uploads to cloud GPU, monitors progress, downloads results.
    """
    import tempfile

    from app.cloud.gpu_client import get_cloud_gpu_client, CloudGPUError
    from app.dicom.anonymizer import DICOMAnonymizer, AnonymizationError

    study_id_str = str(study_id)

    async def progress(pct: int):
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.progress_pct = pct
                await db.commit()
        await manager.send_progress(study_id_str, job_type="totalsegmentator_cloud", pct=pct)

    try:
        temp_base = Path(tempfile.mkdtemp(prefix="radai-cloud-"))
        dicom_dir = temp_base / "dicom"
        anon_dir = temp_base / "anon"
        nifti_path = temp_base / "ct.nii.gz"

        # Get study orthanc_id
        async with AsyncSessionLocal() as db:
            study = await db.get(Study, study_id)
            orthanc_id = study.orthanc_id if study else None

        if not orthanc_id:
            raise CloudGPUError("Study not found or Orthanc ID missing")

        # 1. Download DICOM from Orthanc
        await progress(5)
        dicom_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{settings.orthanc_url}/studies/{orthanc_id}",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()
            series_ids = resp.json().get("Series", [])
            if not series_ids:
                raise CloudGPUError("No series found in Orthanc study")

            series_id = series_ids[0]
            resp = await client.get(
                f"{settings.orthanc_url}/series/{series_id}/instances",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()
            for inst in resp.json():
                inst_id = inst["ID"]
                inst_resp = await client.get(
                    f"{settings.orthanc_url}/instances/{inst_id}/file",
                    auth=(settings.orthanc_user, settings.orthanc_password),
                )
                with open(dicom_dir / f"{inst_id}.dcm", "wb") as f:
                    f.write(inst_resp.content)

        # 2. Anonymize DICOM
        await progress(15)
        anonymizer = DICOMAnonymizer()
        anonymizer.anonymize_directory(
            dicom_dir, anon_dir, progress_callback=lambda pct: progress(15 + int(pct * 0.15))
        )

        # 3. Convert to NIfTI
        await progress(35)
        dicom_series_to_nifti(anon_dir, nifti_path)

        # 4. Run on cloud GPU (full resolution)
        await progress(40)
        cloud_client = get_cloud_gpu_client()
        result = await cloud_client.run_totalsegmentator(
            nifti_path=str(nifti_path),
            full_res=True,
            roi_subset=roi_subset,
            timeout=1200,
            progress_callback=lambda pct: progress(40 + int(pct * 0.5)),
        )

        # 5. Update job status
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "completed"
                job.progress_pct = 100
                job.result_json = result
                job.completed_at = datetime.datetime.now(datetime.UTC)
                await db.commit()

        await manager.send_complete(
            study_id_str,
            job_type="totalsegmentator_cloud",
            result_summary="Cloud TotalSegmentator complete (full resolution)",
        )

    except Exception as exc:
        logger.error("Cloud TotalSegmentator job failed", study_id=study_id, error=str(exc))
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                await db.commit()
        await manager.send_error(
            study_id_str, job_type="totalsegmentator_cloud", error=str(exc)
        )
    finally:
        if "temp_base" in locals():
            shutil.rmtree(temp_base, ignore_errors=True)


async def run_totalsegmentator_job(job_id: UUID, study_id: UUID, roi_subset: list[str] | None = None, fast: bool = True):
    """Run TotalSegmentator in the background and update job status."""
    scheduler = get_scheduler()
    study_id_str = str(study_id)

    async def progress(pct: int):
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.progress_pct = pct
                await db.commit()
        await manager.send_progress(study_id_str, job_type="totalsegmentator", pct=pct)

    try:
        temp_base = Path("/tmp/radai-processing")
        temp_base.mkdir(parents=True, exist_ok=True)
        
        dicom_dir = temp_base / f"{study_id}_dicom"
        dicom_dir.mkdir(parents=True, exist_ok=True)
        input_nifti = temp_base / f"{study_id}.nii.gz"
        output_seg_dir = temp_base / f"{study_id}_seg"

        async with AsyncSessionLocal() as db:
            study = await db.get(Study, study_id)
            orthanc_id = study.orthanc_id if study else None

        if not orthanc_id:
            raise ModelSchedulerError("Study not found in database or Orthanc ID missing")

        # 1. Download DICOM from Orthanc
        await progress(5)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{settings.orthanc_url}/studies/{orthanc_id}", 
                auth=(settings.orthanc_user, settings.orthanc_password)
            )
            resp.raise_for_status()
            series_ids = resp.json().get("Series", [])
            if not series_ids:
                raise ModelSchedulerError("No series found in Orthanc study")
            
            # Select the most suitable series (usually the one with most instances for CT)
            # For now, we take the first one as a baseline
            series_id = series_ids[0]
            
            resp = await client.get(
                f"{settings.orthanc_url}/series/{series_id}/instances", 
                auth=(settings.orthanc_user, settings.orthanc_password)
            )
            resp.raise_for_status()
            instances = resp.json()
            for inst in instances:
                inst_id = inst["ID"]
                inst_resp = await client.get(
                    f"{settings.orthanc_url}/instances/{inst_id}/file", 
                    auth=(settings.orthanc_user, settings.orthanc_password)
                )
                with open(dicom_dir / f"{inst_id}.dcm", "wb") as f:
                    f.write(inst_resp.content)

        # 2. DICOM → NIfTI
        await progress(15)
        dicom_series_to_nifti(dicom_dir, input_nifti)

        # 3. AI Inference
        await progress(25)
        scheduler.run_totalsegmentator(
            input_path=str(input_nifti),
            output_path=str(output_seg_dir),
            roi_subset=roi_subset,
            fast=fast,
            timeout=600,
            progress_callback=progress,
        )

        # 4. Multi-mask NIfTI-SEG → DICOM-SEG
        await progress(85)
        seg_file = temp_base / f"{study_id}_seg.dcm"
        
        # If TotalSegmentator produces multiple files, we need to handle them.
        # For simplicity in Phase 1, we look for 'liver.nii.gz' or the directory.
        mask_files = []
        if output_seg_dir.is_dir():
            mask_files = list(output_seg_dir.glob("*.nii.gz"))
        
        if not mask_files and output_seg_dir.with_suffix(".nii.gz").exists():
            mask_files = [output_seg_dir.with_suffix(".nii.gz")]

        if not mask_files:
            raise ModelSchedulerError("TotalSegmentator completed but no mask files were found")

        # For Phase 1, we still export one DICOM-SEG, but we choose the most relevant or handle a few.
        # Advanced Phase 2 will involve merging masks or creating multi-segment DICOM-SEGs.
        # Pick the largest mask file (usually the one with most data) or 'liver' if it exists.
        target_mask = mask_files[0]
        for f in mask_files:
            if "liver" in f.name.lower():
                target_mask = f
                break
        
        nifti_to_dicom_seg(target_mask, dicom_dir, seg_file, structure_name=target_mask.stem)

        # 5. Upload SEG back to Orthanc
        await progress(95)
        if seg_file.exists():
            async with httpx.AsyncClient(timeout=30) as client:
                with open(seg_file, "rb") as f:
                    resp = await client.post(
                        f"{settings.orthanc_url}/instances",
                        content=f.read(),
                        auth=(settings.orthanc_user, settings.orthanc_password)
                    )
                    resp.raise_for_status()

        # Update DB Job Status
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "completed"
                job.progress_pct = 100
                job.completed_at = datetime.datetime.now(datetime.UTC)
                await db.commit()

        await manager.send_complete(
            study_id_str,
            job_type="totalsegmentator",
            result_summary=f"Segmentation complete ({target_mask.stem})",
        )

    except Exception as exc:
        logger.error("TotalSegmentator job failed", study_id=study_id, error=str(exc))
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                await db.commit()
        await manager.send_error(study_id_str, job_type="totalsegmentator", error=str(exc))
    
    finally:
        # Cleanup
        shutil.rmtree(dicom_dir, ignore_errors=True)
        shutil.rmtree(output_seg_dir, ignore_errors=True)
        input_nifti.unlink(missing_ok=True)
        seg_file.unlink(missing_ok=True)
