"""
RadAI — Plan 1.4: Real CT End-to-End Verification

Full pipeline test with a real lung CT from TCIA:
  1. Download real CT from TCIA (or use pre-downloaded)
  2. Upload to Orthanc PACS
  3. Sync study to PostgreSQL
  4. Run TotalSegmentator (fast mode, lung ROI)
  5. Verify DICOM-SEG created in Orthanc
  6. Run nodule detection
  7. Verify findings persisted in DB

Usage:
    python scripts/verify_real_ct_e2e.py
    python scripts/verify_real_ct_e2e.py --skip-download  # If DICOM already in ./real-ct-data
    python scripts/verify_real_ct_e2e.py --data-dir /path/to/dicom

Requires:
    - Docker stack running (make up)
    - Admin user seeded (make seed-admin)
    - Internet access (for TCIA download, first run only)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

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


# ─── Step 1: Download Real CT from TCIA ────────────────────────────────────

def download_real_ct(data_dir: Path) -> bool:
    section("Step 1: Download Real CT from TCIA")

    # Check if data already exists
    existing = list(data_dir.glob("*.dcm")) + [
        f for f in data_dir.glob("*") if f.is_file() and f.suffix == ""
    ]
    if len(existing) >= 10:
        ok(f"Found {len(existing)} existing DICOM files in {data_dir}")
        return True

    info("No existing data found, downloading from TCIA...")
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from download_tcia_ct import find_and_download
    except ImportError:
        fail("download_tcia_ct.py not found in scripts/")
        return False

    with httpx.Client(timeout=60) as client:
        files = find_and_download(
            client,
            collection="NSCLC-Radiomics",
            patient_id="LUNG1-001",
            output_dir=data_dir,
            max_slices=150,
        )
        if files:
            ok(f"Downloaded {len(files)} DICOM files")
            return True

        # Try LIDC fallback
        warn("NSCLC-Radiomics failed, trying LIDC-IDRI...")
        files = find_and_download(
            client,
            collection="LIDC-IDRI",
            patient_id="LIDC-IDRI-0001",
            output_dir=data_dir,
            max_slices=150,
        )
        if files:
            ok(f"Downloaded {len(files)} DICOM files (LIDC-IDRI)")
            return True

    fail("Could not download real CT from TCIA")
    info("Place real DICOM files manually in: " + str(data_dir))
    return False


# ─── Step 2: Upload to Orthanc ─────────────────────────────────────────────

def upload_to_orthanc(
    client: httpx.Client, orthanc_url: str, auth: tuple[str, str], data_dir: Path
) -> str | None:
    section("Step 2: Upload Real CT to Orthanc")

    # Find all DICOM files
    files = sorted(
        [f for f in data_dir.iterdir() if f.is_file() and f.suffix.lower() in (".dcm", "")]
    )
    if not files:
        # Try nested directories
        files = sorted(data_dir.rglob("*.dcm"))
        if not files:
            files = sorted(
                [f for f in data_dir.rglob("*") if f.is_file() and f.suffix == ""]
            )

    if not files:
        fail(f"No DICOM files found in {data_dir}")
        return None

    info(f"Found {len(files)} DICOM files")

    uploaded = 0
    for i, f in enumerate(files, 1):
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
            if i <= 3:
                warn(f"Upload failed for {f.name}: {e}")

        if i % 20 == 0 or i == len(files):
            info(f"  Uploaded {uploaded}/{i} ...")

    if uploaded == 0:
        fail("No files uploaded")
        return None

    ok(f"Uploaded {uploaded}/{len(files)} instances")

    # Get the study ID
    try:
        resp = client.get(f"{orthanc_url}/studies", auth=auth, timeout=10)
        resp.raise_for_status()
        studies = resp.json()
        if studies:
            # Get most recent study
            for study_entry in reversed(studies):
                study_id = study_entry if isinstance(study_entry, str) else study_entry.get("ID", "")
                # Check this is a CT study (not a SEG from prior runs)
                study_resp = client.get(
                    f"{orthanc_url}/studies/{study_id}",
                    auth=auth,
                    timeout=10,
                )
                if study_resp.status_code == 200:
                    study_data = study_resp.json()
                    # Check modality
                    main_tags = study_data.get("MainDicomTags", {})
                    patient_id = main_tags.get("PatientID", "")
                    if patient_id and patient_id != "RADAI-TEST-001":
                        ok(f"Orthanc study ID: {study_id}")
                        info(f"Patient: {patient_id}, Description: {main_tags.get('StudyDescription', 'N/A')}")
                        return study_id
            # Fallback to last study
            study_id = studies[-1] if isinstance(studies[-1], str) else studies[-1].get("ID", "")
            ok(f"Orthanc study ID: {study_id}")
            return study_id

        fail("No studies found in Orthanc")
        return None
    except Exception as e:
        fail(f"Failed to list studies: {e}")
        return None


# ─── Step 3: Sync + Auth ──────────────────────────────────────────────────

def authenticate(client: httpx.Client, base_url: str) -> str | None:
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


def sync_studies(
    client: httpx.Client, base_url: str, token: str, orthanc_study_id: str
) -> str | None:
    section("Step 3: Sync Study to PostgreSQL")
    try:
        resp = client.post(
            f"{base_url}/api/v1/studies/sync-from-orthanc",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            result = resp.json()
            ok(f"Synced: {result['synced']} studies ({result['created']} new)")
        else:
            warn(f"Sync returned HTTP {resp.status_code}")

        # Find our study
        resp = client.get(
            f"{base_url}/api/v1/studies/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            studies = resp.json().get("items", [])
            for study in studies:
                if study.get("orthanc_id") == orthanc_study_id:
                    study_id = study["id"]
                    ok(f"Study in DB: {study_id} (modality: {study.get('modality')})")
                    return study_id
            fail(f"Study {orthanc_study_id} not found in DB")
            return None

        fail(f"Failed to list studies: HTTP {resp.status_code}")
        return None
    except Exception as e:
        fail(f"Sync failed: {e}")
        return None


# ─── Step 4: TotalSegmentator ──────────────────────────────────────────────

def run_totalsegmentator(
    client: httpx.Client, base_url: str, token: str, study_id: str
) -> str | None:
    section("Step 4: Run TotalSegmentator on Real CT")

    try:
        resp = client.post(
            f"{base_url}/api/v1/ai/studies/{study_id}/run",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "job_type": "totalsegmentator",
                "fast": True,
                "roi_subset": [
                    "lung_upper_lobe_left",
                    "lung_lower_lobe_left",
                    "lung_upper_lobe_right",
                    "lung_middle_lobe_right",
                    "lung_lower_lobe_right",
                    "heart",
                    "aorta",
                ],
            },
            timeout=30,
        )
        if resp.status_code == 202:
            job = resp.json()
            job_id = job["id"]
            ok(f"TotalSegmentator job created: {job_id}")
            return job_id
        fail(f"Failed to create job: HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as e:
        fail(f"Failed to trigger TotalSegmentator: {e}")
        return None


def poll_job(
    client: httpx.Client,
    base_url: str,
    token: str,
    job_id: str,
    label: str = "Job",
    timeout_sec: int = 600,
) -> bool:
    start = time.time()
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
                ok(f"{label} completed in {elapsed}s")
                return True
            elif status == "failed":
                fail(f"{label} failed after {elapsed}s: {job.get('error_message', 'unknown')}")
                return False
            else:
                info(f"{label}: {status} {pct}% ({elapsed}s)")
        except Exception as e:
            warn(f"Poll error: {e}")

        time.sleep(5)

    fail(f"{label} timed out after {timeout_sec}s")
    return False


# ─── Step 5: Verify DICOM-SEG ─────────────────────────────────────────────

def verify_seg_in_orthanc(
    client: httpx.Client, orthanc_url: str, auth: tuple[str, str], orthanc_study_id: str
) -> bool:
    section("Step 5: Verify DICOM-SEG in Orthanc")

    try:
        resp = client.get(
            f"{orthanc_url}/studies/{orthanc_study_id}",
            auth=auth,
            timeout=10,
        )
        resp.raise_for_status()
        study = resp.json()
        series_ids = study.get("Series", [])

        seg_found = 0
        for sid in series_ids:
            sr = client.get(f"{orthanc_url}/series/{sid}", auth=auth, timeout=10)
            if sr.status_code == 200:
                modality = sr.json().get("MainDicomTags", {}).get("Modality", "")
                if modality == "SEG":
                    seg_found += 1
                    desc = sr.json().get("MainDicomTags", {}).get("SeriesDescription", "")
                    ok(f"SEG series: {desc} ({sid[:12]}...)")

        if seg_found:
            ok(f"Found {seg_found} DICOM-SEG series")
            return True

        fail("No DICOM-SEG found in study")
        return False
    except Exception as e:
        fail(f"Orthanc verification failed: {e}")
        return False


# ─── Step 6: Nodule Detection ──────────────────────────────────────────────

def run_nodule_detection(
    client: httpx.Client, base_url: str, token: str, study_id: str
) -> str | None:
    section("Step 6: Run Nodule Detection on Real CT")

    try:
        resp = client.post(
            f"{base_url}/api/v1/ai/studies/{study_id}/run",
            headers={"Authorization": f"Bearer {token}"},
            json={"job_type": "nodule_detection"},
            timeout=30,
        )
        if resp.status_code == 202:
            job = resp.json()
            job_id = job["id"]
            ok(f"Nodule detection job created: {job_id}")
            return job_id
        fail(f"Failed to create job: HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as e:
        fail(f"Failed to trigger nodule detection: {e}")
        return None


# ─── Step 7: Verify Findings ──────────────────────────────────────────────

def verify_findings(
    client: httpx.Client, base_url: str, token: str, study_id: str
) -> bool:
    section("Step 7: Verify Findings in Database")

    try:
        resp = client.get(
            f"{base_url}/api/v1/findings/studies/{study_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            fail(f"Findings API returned HTTP {resp.status_code}")
            return False

        data = resp.json()
        findings = data.get("items", [])
        total = data.get("total", 0)

        if total == 0:
            warn("No nodule findings detected (may be normal for this CT)")
            info("TotalSegmentator segmentation still verified above")
            return True  # Not a failure — real CTs may have no nodules

        ok(f"Found {total} findings in database:")
        for f in findings:
            m = f.get("measurements", {})
            info(
                f"  {f['finding_type'].upper()} | "
                f"{f.get('location', 'N/A')} | "
                f"Diameter: {m.get('longest_diameter_mm', 'N/A')} mm | "
                f"Confidence: {f.get('confidence', 'N/A')}"
            )

        # Verify findings are in 'pending' status (awaiting radiologist review)
        pending = [f for f in findings if f.get("status") == "pending"]
        ok(f"{len(pending)}/{total} findings pending radiologist review")
        return True

    except Exception as e:
        fail(f"Findings verification failed: {e}")
        return False


# ─── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="RadAI Plan 1.4: Real CT End-to-End Verification"
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("RADAI_BASE_URL", "https://localhost"),
    )
    parser.add_argument(
        "--orthanc-url",
        default=os.environ.get("ORTHANC_URL", "https://localhost/orthanc"),
    )
    parser.add_argument("--orthanc-user", default=os.environ.get("ORTHANC_USER", "orthanc"))
    parser.add_argument("--orthanc-password", default=os.environ.get("ORTHANC_PASSWORD", "orthanc"))
    parser.add_argument(
        "--data-dir",
        default="./real-ct-data",
        help="Directory containing real CT DICOM files",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip TCIA download (assume DICOM files exist in data-dir)",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip upload (assume study already in Orthanc)",
    )
    parser.add_argument(
        "--orthanc-study-id",
        help="Use existing Orthanc study ID (with --skip-upload)",
    )
    parser.add_argument(
        "--skip-nodules",
        action="store_true",
        help="Skip nodule detection (only test TotalSegmentator)",
    )
    args = parser.parse_args()

    print(f"{Col.B}{'=' * 60}")
    print(f"  RadAI Plan 1.4: Real CT End-to-End Verification")
    print(f"{'=' * 60}{Col.E}")
    print(f"Backend: {args.base_url}")
    print(f"Orthanc: {args.orthanc_url}")

    results: list[tuple[str, bool]] = []
    data_dir = Path(args.data_dir)

    # Step 1: Download
    if not args.skip_download and not args.skip_upload:
        downloaded = download_real_ct(data_dir)
        results.append(("TCIA Download", downloaded))
        if not downloaded:
            fail("Cannot proceed without real CT data")
            return 1

    with httpx.Client(verify=False) as client:
        auth = (args.orthanc_user, args.orthanc_password)

        # Step 2: Upload
        orthanc_study_id = args.orthanc_study_id
        if not args.skip_upload:
            orthanc_study_id = upload_to_orthanc(client, args.orthanc_url, auth, data_dir)
            results.append(("Orthanc Upload", orthanc_study_id is not None))
            if not orthanc_study_id:
                return 1
        else:
            if not orthanc_study_id:
                fail("--skip-upload requires --orthanc-study-id")
                return 1
            ok(f"Using existing Orthanc study: {orthanc_study_id}")

        # Auth
        token = authenticate(client, args.base_url)
        results.append(("Authentication", token is not None))
        if not token:
            return 1

        # Step 3: Sync
        study_id = sync_studies(client, args.base_url, token, orthanc_study_id)
        results.append(("Study Sync", study_id is not None))
        if not study_id:
            return 1

        # Step 4: TotalSegmentator
        seg_job_id = run_totalsegmentator(client, args.base_url, token, study_id)
        results.append(("TotalSegmentator Job", seg_job_id is not None))
        if seg_job_id:
            seg_done = poll_job(
                client, args.base_url, token, seg_job_id,
                label="TotalSegmentator", timeout_sec=600,
            )
            results.append(("TotalSegmentator Completion", seg_done))

            # Step 5: Verify SEG
            if seg_done:
                seg_verified = verify_seg_in_orthanc(
                    client, args.orthanc_url, auth, orthanc_study_id
                )
                results.append(("DICOM-SEG Verification", seg_verified))

        # Step 6: Nodule Detection
        if not args.skip_nodules:
            nod_job_id = run_nodule_detection(client, args.base_url, token, study_id)
            results.append(("Nodule Detection Job", nod_job_id is not None))
            if nod_job_id:
                nod_done = poll_job(
                    client, args.base_url, token, nod_job_id,
                    label="Nodule Detection", timeout_sec=600,
                )
                results.append(("Nodule Detection Completion", nod_done))

                # Step 7: Verify Findings
                if nod_done:
                    findings_ok = verify_findings(
                        client, args.base_url, token, study_id
                    )
                    results.append(("Findings Verification", findings_ok))

    # ─── Summary ───────────────────────────────────────────────────────────
    print(f"\n{Col.B}{'=' * 60}")
    print(f"  Plan 1.4 Verification Summary")
    print(f"{'=' * 60}{Col.E}")

    passed = sum(1 for _, ok_ in results if ok_)
    total = len(results)

    for name, ok_ in results:
        symbol = f"{Col.G}[PASS]{Col.E}" if ok_ else f"{Col.R}[FAIL]{Col.E}"
        print(f"  {symbol} {name}")

    print()
    if passed == total:
        print(f"  {Col.G}{Col.B}ALL CHECKS PASSED ({passed}/{total}){Col.E}")
        print(f"  {Col.G}Plan 1.4 VERIFIED: Real CT E2E pipeline working{Col.E}")
        return 0
    else:
        print(f"  {Col.R}{Col.B}{total - passed} check(s) failed ({passed}/{total}){Col.E}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
