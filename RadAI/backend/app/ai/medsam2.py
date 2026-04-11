"""RadAI — Vision Agent wrapper for LiteMedSAM (Local Execution)."""

import structlog
from typing import Optional, Dict, Any
from app.scheduler import get_scheduler, ModelSchedulerError

logger = structlog.get_logger(__name__)

class MedSAM2Agent:
    """Wrapper for the local LiteMedSAM inference service.
    
    By executing locally and using the ModelScheduler, we preserve patient privacy
    and successfully operate within the 8 GB GPU VRAM limit by unloading other 
    models (like nnInteractive or TotalSegmentator) beforehand.
    """

    async def segment_bbox(self, image_path: str, bbox: list[int]) -> Optional[Dict[str, Any]]:
        """
        Request segmentation using a bounding box.

        Args:
            image_path: Path to the NIfTI file.
            bbox: [x_min, y_min, x_max, y_max]

        Returns:
            JSON Dict containing segmentation mask path and metadata,
            or None on failure.
        """
        scheduler = get_scheduler()
        try:
            # Scheduler will automatically unload other models to free VRAM for MedSAM
            model = scheduler.load_litemedsam()

            # Execute real inference
            if hasattr(model, 'segment_bbox'):
                result = model.segment_bbox(image_path, bbox)
                # result is {"status": "success", "mask_path": "...", "slice_index": N, ...}
                return result
            else:
                logger.error("Loaded model does not have segment_bbox method")
                return None
        except ModelSchedulerError as exc:
            logger.error(f"LiteMedSAM inference failed: {exc}")
            return None
        except Exception as exc:
            logger.error(f"Unexpected error during LiteMedSAM bounding box: {exc}")
            return None
