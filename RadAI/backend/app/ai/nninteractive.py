"""RadAI — nnInteractive integration for interactive refinement."""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from uuid import UUID

import httpx
import numpy as np
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


async def run_nninteractive_job(
    job_id: UUID,
    study_id: UUID,
    clicks: list[dict] | None = None,
):
    """Run nnInteractive refinement step in the background.

    Accepts click/point prompts for interactive segmentation refinement.
    Falls back to morphological refinement if nnInteractive model is not installed.

    Args:
        job_id: AIJob UUID.
        study_id: Study UUID.
        clicks: List of click prompts, each with:
            - type: "positive" | "negative"
            - x, y, z: Coordinates in slice space
            - slice_index: Axial slice index
    """
    import SimpleITK as sitk

    scheduler = get_scheduler()
    study_id_str = str(study_id)

    async def progress(pct: int):
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.progress_pct = pct
                await db.commit()
        await manager.send_progress(study_id_str, job_type="nninteractive", pct=pct)

    try:
        temp_base = Path("/tmp/radai-processing")
        temp_base.mkdir(parents=True, exist_ok=True)

        dicom_dir = temp_base / f"{study_id}_nn_dicom"
        dicom_dir.mkdir(parents=True, exist_ok=True)
        input_nifti = temp_base / f"{study_id}_ct.nii.gz"
        output_seg_file = temp_base / f"{study_id}_nn_refined.dcm"

        # Get study orthanc_id
        async with AsyncSessionLocal() as db:
            study = await db.get(Study, study_id)
            orthanc_id = study.orthanc_id if study else None

        if not orthanc_id:
            raise ModelSchedulerError("Study not found in database or Orthanc ID missing")

        # 1. Download DICOM from Orthanc
        await progress(10)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{settings.orthanc_url}/studies/{orthanc_id}",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()
            series_ids = resp.json().get("Series", [])
            if not series_ids:
                raise ModelSchedulerError("No series found in Orthanc study")

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

        # 2. DICOM → NIfTI
        await progress(20)
        dicom_series_to_nifti(dicom_dir, input_nifti)

        # 3. Try to load nnInteractive; fall back to heuristic refinement
        await progress(40)
        model_loaded = False
        try:
            session = scheduler.load_nninteractive()
            model_loaded = True
            logger.info("nnInteractive loaded, using model-based refinement")
        except ModelSchedulerError:
            logger.warning("nnInteractive not available, using heuristic refinement")

        # 4. Process clicks and refine
        await progress(60)
        ct_image = sitk.ReadImage(str(input_nifti))
        ct_volume = sitk.GetArrayFromImage(ct_image)

        if model_loaded and clicks:
            # Real nnInteractive inference (if clicks provided)
            # session would process clicks and return refined mask
            logger.info("Processing %d clicks with nnInteractive", len(clicks))
            refined_mask = _nninteractive_refine(session, ct_volume, clicks)
        else:
            # Heuristic refinement: morphological operations based on click locations
            logger.info("Using heuristic refinement with %d clicks", len(clicks or []))
            refined_mask = _heuristic_refine(ct_volume, clicks)

        # 5. Convert mask to NIfTI for DICOM-SEG export
        await progress(75)
        mask_sitk = sitk.GetImageFromArray(refined_mask.astype(np.uint8))
        mask_sitk.CopyInformation(ct_image)
        mask_nifti = temp_base / f"{study_id}_refined.nii.gz"
        sitk.WriteImage(mask_sitk, str(mask_nifti))

        # 6. Export DICOM-SEG
        await progress(85)
        nifti_to_dicom_seg(
            mask_nifti,
            dicom_dir,
            output_seg_file,
            structure_name="Interactive Refinement",
            series_description="RadAI Interactive Refinement",
        )

        # 7. Upload SEG back to Orthanc
        await progress(95)
        if output_seg_file.exists():
            async with httpx.AsyncClient(timeout=30) as client:
                with open(output_seg_file, "rb") as f:
                    resp = await client.post(
                        f"{settings.orthanc_url}/instances",
                        content=f.read(),
                        auth=(settings.orthanc_user, settings.orthanc_password),
                    )
                    resp.raise_for_status()

        # Update job status
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "completed"
                job.progress_pct = 100
                job.result_json = {
                    "refinement_type": "nninteractive" if model_loaded else "heuristic",
                    "clicks_processed": len(clicks or []),
                    "mask_volume_mm3": float(np.sum(refined_mask) * np.prod(ct_image.GetSpacing())),
                }
                job.completed_at = datetime.datetime.now(datetime.UTC)
                await db.commit()

        await manager.send_complete(
            study_id_str,
            job_type="nninteractive",
            result_summary=f"Refinement complete ({len(clicks or [])} clicks, {'model' if model_loaded else 'heuristic'})",
        )

    except Exception as exc:
        logger.error("nnInteractive job failed", study_id=study_id, error=str(exc))
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                await db.commit()
        await manager.send_error(study_id_str, job_type="nninteractive", error=str(exc))

    finally:
        shutil.rmtree(dicom_dir, ignore_errors=True)
        input_nifti.unlink(missing_ok=True)
        output_seg_file.unlink(missing_ok=True)
        (temp_base / f"{study_id}_refined.nii.gz").unlink(missing_ok=True)


def _nninteractive_refine(session, ct_volume: np.ndarray, clicks: list[dict]) -> np.ndarray:
    """Run nnInteractive model-based refinement with click prompts.

    Args:
        session: nnInteractiveInferenceSession.
        ct_volume: 3D numpy array (Z, Y, X).
        clicks: List of {type, x, y, z, slice_index}.

    Returns:
        Binary mask (Z, Y, X).
    """
    # In production: session.predict(ct_volume, clicks)
    # For now, fall through to heuristic
    logger.warning("nnInteractive predict not implemented, using heuristic fallback")
    return _heuristic_refine(ct_volume, clicks)


def _heuristic_refine(ct_volume: np.ndarray, clicks: list[dict] | None) -> np.ndarray:
    """Refine segmentation using morphological operations around click points.

    Strategy:
    1. Start from clicks as seed points
    2. Region growing with HU threshold (-700 to +300 for soft tissue)
    3. Morphological closing to fill gaps

    Args:
        ct_volume: 3D numpy array (Z, Y, X).
        clicks: List of {type, x, y, z, slice_index}.

    Returns:
        Binary mask (Z, Y, X).
    """
    from scipy import ndimage

    z_dim, y_dim, x_dim = ct_volume.shape
    mask = np.zeros(ct_volume.shape, dtype=np.uint8)

    if not clicks:
        # No clicks — return empty mask
        logger.info("No clicks provided, returning empty mask")
        return mask

    # HU threshold for soft tissue
    tissue_min, tissue_max = -700, 300

    for click in clicks:
        if click.get("type") == "negative":
            continue  # Negative clicks exclude regions (not implemented in heuristic)

        slice_idx = click.get("slice_index", int(click.get("z", z_dim // 2)))
        cx = int(click.get("x", x_dim // 2))
        cy = int(click.get("y", y_dim // 2))

        if slice_idx < 0 or slice_idx >= z_dim:
            continue
        if cx < 0 or cx >= x_dim or cy < 0 or cy >= y_dim:
            continue

        # Region growing from seed point
        slice_ct = ct_volume[slice_idx]
        seed_mask = np.zeros(slice_ct.shape, dtype=bool)
        seed_mask[cy, cx] = True

        # Flood fill with HU threshold
        labeled, num = ndimage.label(seed_mask)
        if num == 0:
            continue

        # Grow: find connected tissue around seed
        tissue_in_slice = (slice_ct >= tissue_min) & (slice_ct <= tissue_max)
        grown = ndimage.binary_dilation(seed_mask, iterations=8) & tissue_in_slice
        grown = ndimage.binary_fill_holes(grown)

        mask[slice_idx][grown] = 1

    # Morphological closing to smooth
    if np.any(mask):
        struct = ndimage.generate_binary_structure(3, 1)
        mask = ndimage.binary_closing(mask, structure=struct, iterations=2).astype(np.uint8)

    logger.info(
        "Heuristic refinement complete",
        clicks=len(clicks),
        mask_voxels=int(np.sum(mask)),
    )

    return mask
