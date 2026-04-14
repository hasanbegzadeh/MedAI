"""RadAI — PACS (Orthanc) Service."""

from pathlib import Path
import httpx
import structlog
from app.config import Settings

logger = structlog.get_logger(__name__)


class PACSService:
    """Service for interacting with the Orthanc PACS server."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.auth = (settings.orthanc_user, settings.orthanc_password)
        self.base_url = str(settings.orthanc_url).rstrip("/")

    async def get_study_series(self, orthanc_id: str) -> list[str]:
        """Return list of series IDs for a given Orthanc study ID."""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{self.base_url}/studies/{orthanc_id}",
                auth=self.auth,
            )
            resp.raise_for_status()
            return resp.json().get("Series", [])

    async def download_series_to_dir(self, series_id: str, dest_dir: Path) -> list[Path]:
        """Download all instances for a series to the specified directory."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []

        async with httpx.AsyncClient(timeout=60) as client:
            # 1. Get instance list
            resp = await client.get(
                f"{self.base_url}/series/{series_id}/instances",
                auth=self.auth,
            )
            resp.raise_for_status()
            instances = resp.json()

            # 2. Download each instance
            for inst in instances:
                inst_id = inst["ID"]
                inst_resp = await client.get(
                    f"{self.base_url}/instances/{inst_id}/file",
                    auth=self.auth,
                )
                inst_resp.raise_for_status()

                file_path = dest_dir / f"{inst_id}.dcm"
                with open(file_path, "wb") as f:
                    f.write(inst_resp.content)
                downloaded.append(file_path)

        logger.info(
            "Series downloaded",
            series_id=series_id,
            instance_count=len(downloaded),
            dest_dir=str(dest_dir),
        )
        return downloaded
