"""
RadAI — Download Real CT Study from TCIA (The Cancer Imaging Archive)

Downloads a small real lung CT from the NSCLC-Radiomics public collection
for end-to-end testing of TotalSegmentator and the nodule detection pipeline.

The TCIA REST API v2 provides public access without authentication for
open-access collections.

Usage:
    python scripts/download_tcia_ct.py
    python scripts/download_tcia_ct.py --output-dir ./real-ct-data
    python scripts/download_tcia_ct.py --collection NSCLC-Radiomics --max-slices 80

TCIA API docs: https://wiki.cancerimagingarchive.net/display/Public/TCIA+Programmatic+Interface
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import zipfile
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


class C:
    G = "\033[92m"
    R = "\033[91m"
    Y = "\033[93m"
    B = "\033[1m"
    E = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {C.G}[OK]{C.E} {msg}")


def fail(msg: str) -> None:
    print(f"  {C.R}[FAIL]{C.E} {msg}")


def warn(msg: str) -> None:
    print(f"  {C.Y}[WARN]{C.E} {msg}")


def info(msg: str) -> None:
    print(f"  \033[96m[INFO]\033[0m {msg}")


TCIA_BASE = "https://services.cancerimagingarchive.net/nbia-api/services/v2"

# Known small CT series from public collections for testing.
# These are real lung CTs with 50-130 slices — small enough for fast
# testing but real enough for TotalSegmentator validation.
KNOWN_SERIES = [
    {
        "collection": "NSCLC-Radiomics",
        "patient_id": "LUNG1-001",
        "description": "NSCLC lung CT (Radiomics collection)",
    },
    {
        "collection": "LIDC-IDRI",
        "patient_id": "LIDC-IDRI-0001",
        "description": "LIDC lung CT (nodule screening dataset)",
    },
]


def list_series_for_patient(
    client: httpx.Client, collection: str, patient_id: str
) -> list[dict]:
    """Query TCIA for CT series belonging to a patient."""
    resp = client.get(
        f"{TCIA_BASE}/getSeries",
        params={
            "Collection": collection,
            "PatientID": patient_id,
            "Modality": "CT",
            "format": "json",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    return resp.json()


def download_series(
    client: httpx.Client, series_uid: str, output_dir: Path
) -> list[Path]:
    """Download a DICOM series as a ZIP from TCIA and extract it."""
    info(f"Downloading series {series_uid[:40]}...")
    resp = client.get(
        f"{TCIA_BASE}/getImage",
        params={"SeriesInstanceUID": series_uid},
        timeout=120,
    )
    if resp.status_code != 200:
        fail(f"Download failed: HTTP {resp.status_code}")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    # TCIA returns a ZIP file
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        extracted = []
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            # Extract to flat directory with clean names
            data = zf.read(name)
            out_name = Path(name).name
            if not out_name:
                continue
            out_path = output_dir / out_name
            out_path.write_bytes(data)
            extracted.append(out_path)
        return extracted
    except zipfile.BadZipFile:
        # Sometimes TCIA returns raw DICOM files, not a ZIP
        # Save the entire response as a single DICOM file
        out_path = output_dir / "instance_001.dcm"
        out_path.write_bytes(resp.content)
        return [out_path]


def find_and_download(
    client: httpx.Client,
    collection: str,
    patient_id: str,
    output_dir: Path,
    max_slices: int = 150,
) -> list[Path]:
    """Find a suitable CT series and download it."""
    info(f"Querying TCIA for {collection}/{patient_id}...")
    series_list = list_series_for_patient(client, collection, patient_id)

    if not series_list:
        warn(f"No CT series found for {patient_id} in {collection}")
        return []

    # Pick the series with the most slices under max_slices, or the smallest one
    suitable = [
        s for s in series_list if int(s.get("ImageCount", 0)) <= max_slices
    ]
    if not suitable:
        # Fall back to smallest series
        suitable = sorted(series_list, key=lambda s: int(s.get("ImageCount", 0)))

    chosen = suitable[0]
    series_uid = chosen["SeriesInstanceUID"]
    image_count = int(chosen.get("ImageCount", 0))
    body_part = chosen.get("BodyPartExamined", "unknown")

    ok(f"Found: {body_part} CT, {image_count} slices")
    info(f"Series UID: {series_uid}")

    return download_series(client, series_uid, output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a real CT study from TCIA for RadAI testing"
    )
    parser.add_argument(
        "--output-dir",
        default="./real-ct-data",
        help="Output directory for DICOM files",
    )
    parser.add_argument(
        "--collection",
        default="NSCLC-Radiomics",
        help="TCIA collection name (default: NSCLC-Radiomics)",
    )
    parser.add_argument(
        "--patient-id",
        default="LUNG1-001",
        help="TCIA patient ID (default: LUNG1-001)",
    )
    parser.add_argument(
        "--max-slices",
        type=int,
        default=150,
        help="Maximum number of slices to accept (default: 150)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list available series, don't download",
    )
    args = parser.parse_args()

    print(f"{C.B}== RadAI Real CT Download (TCIA) =={C.E}")
    print(f"Collection: {args.collection}")
    print(f"Patient: {args.patient_id}")

    output_dir = Path(args.output_dir)

    with httpx.Client(timeout=60) as client:
        if args.list_only:
            info("Listing available series...")
            series_list = list_series_for_patient(
                client, args.collection, args.patient_id
            )
            if not series_list:
                fail("No CT series found")
                return 1
            print(f"\n  Found {len(series_list)} CT series:")
            for s in series_list:
                print(
                    f"    {s.get('BodyPartExamined', '?'):12s} "
                    f"{s.get('ImageCount', '?'):>4s} slices  "
                    f"{s['SeriesInstanceUID'][:40]}..."
                )
            return 0

        # Try primary collection/patient first
        files = find_and_download(
            client, args.collection, args.patient_id, output_dir, args.max_slices
        )

        # If primary fails, try fallbacks
        if not files:
            warn("Primary download failed, trying fallback sources...")
            for fallback in KNOWN_SERIES:
                if (
                    fallback["collection"] == args.collection
                    and fallback["patient_id"] == args.patient_id
                ):
                    continue  # Skip already-tried source
                info(f"Trying {fallback['description']}...")
                files = find_and_download(
                    client,
                    fallback["collection"],
                    fallback["patient_id"],
                    output_dir,
                    args.max_slices,
                )
                if files:
                    break

        if not files:
            fail("Could not download any real CT from TCIA")
            info("Check your internet connection or try a different collection")
            info("Alternatively, place DICOM files manually in the output directory")
            return 1

        # Verify DICOM files
        dcm_files = [f for f in files if f.suffix.lower() in (".dcm", "")]
        ok(f"Downloaded {len(dcm_files)} DICOM files to {output_dir}")

        # Quick validation with pydicom
        try:
            import pydicom

            ds = pydicom.dcmread(str(dcm_files[0]), stop_before_pixels=True)
            ok(
                f"Validated: {ds.PatientID} | {ds.Modality} | "
                f"{ds.get('BodyPartExamined', 'N/A')} | "
                f"{ds.Rows}x{ds.Columns}"
            )
        except ImportError:
            warn("pydicom not installed, skipping validation")
        except Exception as e:
            warn(f"Validation warning: {e}")

        print(f"\n{C.B}Next steps:{C.E}")
        print(f"  1. Upload to Orthanc:")
        print(f"     python scripts/upload_test_dicom.py {output_dir}")
        print(f"  2. Run E2E verification:")
        print(f"     python scripts/verify_real_ct_e2e.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
