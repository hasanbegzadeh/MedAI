"""
RadAI — Plan 1.2: E2E DICOM → NIfTI → SEG Pipeline Verification

Tests the complete AI segmentation workflow:
  1. Upload synthetic CT to Orthanc
  2. Create Study record in PostgreSQL
  3. Trigger TotalSegmentator via POST /api/v1/ai/studies/{id}/run
  4. Poll job status until completed
  5. Verify DICOM-SEG appears in Orthanc

Usage:
    python scripts/verify_e2e_segmentation.py
    python scripts/verify_e2e_segmentation.py --base-url https://localhost
    python scripts/verify_e2e_segmentation.py --skip-upload  # If DICOM already uploaded

Requires:
    - Docker stack running (make up)
    - Admin user seeded (make seed-admin)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from uuid import UUID

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


class Col:
    G = "\033[92m"
    R = "\033[91m"
    Y = "\033[93m"
    B = "\033[1m"
    C = "\033[96m"
    E = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {Col.G}[OK]{Col.E} {msg}")


def fail(msg: str) -> None:
    print(f"  {Col.R}[FAIL]{Col.E} {msg}")


def warn(msg: str) -> None:
    print(f"  {Col.Y}[WARN]{Col.E} {msg}")


def info(msg: str) -> None:
    print(f"  {Col.C}[INFO]{Col.E} {msg}")


def section(title: str) -> None:
    print(f"\n{Col.B}{Col.C}=== {title} ==={Col.E}")


# ─── Step 1: Upload Synthetic CT ─────────────────────────────────────────────
def upload_synthetic_ct(client: httpx.Client, orthanc_url: str, auth: tuple[str, str]) -> str | None:
    section("Step 1: Upload Synthetic CT to Orthanc")

    # Import the synthetic generation from upload_test_dicom
    sys.path.insert(0, str(Path(__file__).parent))
    from upload_test_dicom import generate_synthetic_ct

    out_dir = Path(__file__).parent.parent.parent / "temp-synthetic-dicom"
    info(f"Generating synthetic CT in {out_dir} ...")
    files = generate_synthetic_ct(out_dir, num_slices=32)
    ok(f"Generated {len(files)} synthetic DICOM slices")

    # Upload to Orthanc
    uploaded = 0
    for f in files:
        try:
            with open(f, "rb") as fh:
                resp = client.post(
                    f"{orthanc_url}/instances",
                    content=fh.read(),
                    headers={"Content-Type": "application/dicom"},
                    auth=auth,
                    timeout=30,
                )
                if resp.status_code in (200, 201):
                    uploaded += 1
        except Exception as e:
            warn(f"Failed to upload {f.name}: {e}")

    if uploaded == len(files):
        ok(f"All {uploaded} instances uploaded")
    else:
        fail(f"Only {uploaded}/{len(files)} uploaded")
        return None

    # Get the study ID from Orthanc
    try:
        resp = client.get(f"{orthanc_url}/studies", auth=auth, timeout=10)
        resp.raise_for_status()
        studies = resp.json()
        if studies:
            # Get the most recent study (our synthetic one)
            study = studies[-1]
            orthanc_study_id = study["ID"]
            ok(f"Orthanc study ID: {orthanc_study_id}")
            return orthanc_study_id
        fail("No studies found in Orthanc")
        return None
    except Exception as e:
        fail(f"Failed to list studies: {e}")
        return None


# ─── Step 2: Sync Studies from Orthanc ───────────────────────────────────────
def sync_studies_from_orthanc(client: httpx.Client, base_url: str, token: str, orthanc_study_id: str) -> str | None:
    section("Step 2: Sync Studies from Orthanc to PostgreSQL")

    try:
        # Trigger sync
        resp = client.post(
            f"{base_url}/api/v1/studies/sync-from-orthanc",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            sync_result = resp.json()
            ok(f"Synced {sync_result['synced']} studies ({sync_result['created']} created, {sync_result['updated']} updated)")
        else:
            warn(f"Sync returned HTTP {resp.status_code}")

        # Now fetch studies to find our orthanc study
        resp = client.get(
            f"{base_url}/api/v1/studies/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            studies_data = resp.json()
            studies = studies_data.get("items", [])
            
            # Find our study by orthanc_id
            for study in studies:
                if study.get("orthanc_id") == orthanc_study_id:
                    study_id = study["id"]
                    ok(f"Found study in DB: {study_id} (modality: {study.get('modality')})")
                    return study_id
            
            fail(f"Study with orthanc_id {orthanc_study_id} not found in DB after sync")
            info(f"Available studies: {[s.get('orthanc_id') for s in studies]}")
            return None
        
        fail(f"Failed to list studies: HTTP {resp.status_code}")
        return None
    except Exception as e:
        fail(f"Study sync failed: {e}")
        return None


# ─── Step 3: Trigger AI Job ──────────────────────────────────────────────────
def trigger_ai_job(client: httpx.Client, base_url: str, token: str, study_id: str) -> str | None:
    section("Step 3: Trigger TotalSegmentator Job")

    try:
        resp = client.post(
            f"{base_url}/api/v1/ai/studies/{study_id}/run",
            headers={"Authorization": f"Bearer {token}"},
            json={"job_type": "totalsegmentator", "fast": True, "body_seg": True},
            timeout=30,
        )
        if resp.status_code == 202:
            job = resp.json()
            job_id = job["id"]
            ok(f"AI job created: {job_id}")
            ok(f"Status: {job['status']}, Progress: {job['progress_pct']}%")
            return job_id
        fail(f"Failed to create job: HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as e:
        fail(f"Failed to trigger AI job: {e}")
        return None


# ─── Step 4: Poll Job Status ─────────────────────────────────────────────────
def poll_job_status(client: httpx.Client, base_url: str, token: str, job_id: str, timeout_sec: int = 600) -> bool:
    section("Step 4: Poll Job Status")

    start = time.time()
    poll_interval = 5  # seconds

    while time.time() - start < timeout_sec:
        elapsed = int(time.time() - start)
        try:
            resp = client.get(
                f"{base_url}/api/v1/ai/jobs/{job_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            resp.raise_for_status()
            job = resp.json()
            status = job["status"]
            pct = job["progress_pct"]

            if status == "completed":
                ok(f"Job completed in {elapsed}s (progress: {pct}%)")
                return True
            elif status == "failed":
                fail(f"Job failed after {elapsed}s: {job.get('error_message', 'unknown error')}")
                return False
            elif status in ("queued", "running"):
                info(f"Job {status}... {pct}% ({elapsed}s elapsed)")
            else:
                warn(f"Unknown status: {status}")

        except Exception as e:
            warn(f"Poll failed: {e}")

        time.sleep(poll_interval)

    fail(f"Job did not complete within {timeout_sec}s timeout")
    return False


# ─── Step 5: Verify DICOM-SEG in Orthanc ─────────────────────────────────────
def verify_dicom_seg_in_orthanc(client: httpx.Client, orthanc_url: str, auth: tuple[str, str], orthanc_study_id: str) -> bool:
    section("Step 5: Verify DICOM-SEG in Orthanc")

    try:
        # Get the study details to see new series
        resp = client.get(
            f"{orthanc_url}/studies/{orthanc_study_id}",
            auth=auth,
            timeout=10,
        )
        resp.raise_for_status()
        study = resp.json()
        series = study.get("Series", [])

        seg_series = []
        for series_id in series:
            series_resp = client.get(
                f"{orthanc_url}/series/{series_id}",
                auth=auth,
                timeout=10,
            )
            if series_resp.status_code == 200:
                series_data = series_resp.json()
                modality = series_data.get("MainDicomTags", {}).get("Modality", "")
                if modality == "SEG":
                    seg_series.append(series_id)

        if seg_series:
            ok(f"Found {len(seg_series)} DICOM-SEG series in Orthanc")
            for s in seg_series:
                ok(f"  - SEG Series ID: {s}")
            return True
        else:
            fail("No DICOM-SEG series found in Orthanc study")
            info("Available series modalities:")
            for series_id in series:
                series_resp = client.get(
                    f"{orthanc_url}/series/{series_id}",
                    auth=auth,
                    timeout=10,
                )
                if series_resp.status_code == 200:
                    series_data = series_resp.json()
                    modality = series_data.get("MainDicomTags", {}).get("Modality", "unknown")
                    info(f"  - {series_id}: Modality={modality}")
            return False

    except Exception as e:
        fail(f"Failed to verify Orthanc study: {e}")
        return False


# ─── Authentication Helper ───────────────────────────────────────────────────
def get_admin_token(client: httpx.Client, base_url: str) -> str | None:
    try:
        resp = client.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": "admin", "password": "changeme"},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        ok("Admin authentication successful")
        return token
    except Exception as e:
        fail(f"Authentication failed: {e}")
        return None


# ─── Main ────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="RadAI E2E Segmentation Pipeline Verification")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("RADAI_BASE_URL", "https://localhost"),
        help="Base URL of the Nginx gateway",
    )
    parser.add_argument(
        "--orthanc-url",
        default=os.environ.get("ORTHANC_URL", "https://localhost/orthanc"),
        help="Orthanc PACS URL",
    )
    parser.add_argument(
        "--orthanc-user",
        default=os.environ.get("ORTHANC_USER", "orthanc"),
    )
    parser.add_argument(
        "--orthanc-password",
        default=os.environ.get("ORTHANC_PASSWORD", "orthanc"),
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip DICOM upload (assume already present)",
    )
    parser.add_argument(
        "--study-id",
        help="Use existing study ID (UUID) instead of creating one",
    )
    parser.add_argument(
        "--orthanc-study-id",
        help="Use existing Orthanc study ID",
    )
    args = parser.parse_args()

    print(f"{Col.B}=== RadAI Plan 1.2: E2E Segmentation Pipeline Verification ==={Col.E}")
    print(f"Backend: {args.base_url}")
    print(f"Orthanc: {args.orthanc_url}")

    results: list[tuple[str, bool]] = []

    with httpx.Client(verify=False) as client:
        auth = (args.orthanc_user, args.orthanc_password)
        orthanc_study_id = args.orthanc_study_id

        # Step 1: Upload synthetic CT (unless skipped)
        if not args.skip_upload:
            orthanc_study_id = upload_synthetic_ct(client, args.orthanc_url, auth)
            results.append(("Synthetic CT Upload", orthanc_study_id is not None))
            if not orthanc_study_id:
                fail("Cannot proceed without uploaded DICOM")
                return 1
        else:
            if not orthanc_study_id:
                fail("--skip-upload requires --orthanc-study-id")
                return 1
            ok(f"Using existing Orthanc study: {orthanc_study_id}")

        # Step 2: Get auth token
        token = get_admin_token(client, args.base_url)
        results.append(("Authentication", token is not None))
        if not token:
            fail("Cannot proceed without authentication")
            return 1

        # Step 2: Sync studies from Orthanc
        study_id = sync_studies_from_orthanc(client, args.base_url, token, orthanc_study_id)
        results.append(("Study Sync", study_id is not None))
        if not study_id:
            fail("Cannot proceed without study record")
            return 1

        # Step 3: Trigger AI job
        job_id = trigger_ai_job(client, args.base_url, token, study_id)
        results.append(("AI Job Creation", job_id is not None))
        if not job_id:
            fail("Cannot proceed without AI job")
            return 1

        # Step 4: Poll job status
        completed = poll_job_status(client, args.base_url, token, job_id)
        results.append(("AI Job Completion", completed))
        if not completed:
            fail("Job did not complete successfully")
            return 1

        # Step 5: Verify DICOM-SEG
        seg_verified = verify_dicom_seg_in_orthanc(client, args.orthanc_url, auth, orthanc_study_id)
        results.append(("DICOM-SEG Verification", seg_verified))

    # Summary
    print(f"\n{Col.B}=== Summary ==={Col.E}")
    passed = sum(1 for _, ok_ in results if ok_)
    total = len(results)

    for name, ok_ in results:
        symbol = f"{Col.G}[OK]{Col.E}" if ok_ else f"{Col.R}[FAIL]{Col.E}"
        print(f"  {symbol} {name}")

    if passed == total:
        print(f"\n{Col.G}{Col.B}All checks passed ({passed}/{total}){Col.E}")
        print(f"{Col.G}Plan 1.2 VERIFIED: E2E DICOM → NIfTI → SEG pipeline working{Col.E}")
        return 0
    else:
        print(f"\n{Col.R}{Col.B}{total - passed} check(s) failed ({passed}/{total} passing){Col.E}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
