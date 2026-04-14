"""
RadAI — Upload Test DICOM to Orthanc

Uploads DICOM files to the local Orthanc PACS for end-to-end testing of
the OHIF viewer and the AI pipeline.

Supports two modes:

  1. Upload a directory or file you already have:
       python scripts/upload_test_dicom.py /path/to/dicom_folder

  2. Generate and upload a small synthetic CT study (default, no external
     dependencies beyond numpy + pydicom). Useful for smoke-testing the
     viewer when you do not yet have sample data on disk:
       python scripts/upload_test_dicom.py --synthetic

  3. Download a real lung CT from TCIA and upload it:
       python scripts/upload_test_dicom.py --tcia

The script uses the Orthanc REST API POST /instances with basic auth.
Credentials and base URL come from environment variables (or CLI flags):

    ORTHANC_URL       default: https://localhost/orthanc
    ORTHANC_USER      default: orthanc
    ORTHANC_PASSWORD  default: orthanc
"""
from __future__ import annotations

import argparse
import os
import sys
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


# ─── DICOM discovery ─────────────────────────────────────────────────────────
def iter_dicom_files(path: Path):
    if path.is_file():
        yield path
        return
    for f in sorted(path.rglob("*")):
        if not f.is_file():
            continue
        # Accept .dcm, .DCM, and extensionless files under a DICOMDIR-style tree
        if f.suffix.lower() in (".dcm", ".ima") or f.suffix == "":
            yield f


# ─── Synthetic DICOM generation ──────────────────────────────────────────────
def generate_synthetic_ct(out_dir: Path, num_slices: int = 32) -> list[Path]:
    """
    Create a small synthetic CT series for smoke testing.
    Produces num_slices 128x128 axial images with a centered sphere.
    """
    try:
        import numpy as np
        import pydicom
        from pydicom.dataset import Dataset, FileDataset
        from pydicom.uid import generate_uid, ExplicitVRLittleEndian
    except ImportError:
        print("ERROR: synthetic mode requires numpy and pydicom")
        print("Install with: pip install numpy pydicom")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    study_uid = generate_uid()
    series_uid = generate_uid()
    frame_of_reference_uid = generate_uid()

    rows, cols = 128, 128
    center = np.array([rows / 2, cols / 2])
    radius = 30

    for i in range(num_slices):
        sop_uid = generate_uid()

        # Build a volumetric sphere slice
        y, x = np.ogrid[:rows, :cols]
        dist = np.sqrt((x - center[1]) ** 2 + (y - center[0]) ** 2)
        slice_img = np.full((rows, cols), -1000, dtype=np.int16)  # air background
        z_dist = abs(i - num_slices / 2)
        slice_radius2 = max(0, radius ** 2 - z_dist ** 2)
        if slice_radius2 > 0:
            mask = dist ** 2 <= slice_radius2
            slice_img[mask] = 40  # soft tissue HU

        # Build the FileDataset
        file_meta = Dataset()
        file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage
        file_meta.MediaStorageSOPInstanceUID = sop_uid
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        fp = out_dir / f"slice_{i:03d}.dcm"
        ds = FileDataset(str(fp), {}, file_meta=file_meta, preamble=b"\0" * 128)

        # Patient / Study / Series identifiers
        ds.PatientName = "TEST^RADAI"
        ds.PatientID = "RADAI-TEST-001"
        ds.PatientBirthDate = "19700101"
        ds.PatientSex = "O"
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.SOPInstanceUID = sop_uid
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        ds.StudyID = "1"
        ds.SeriesNumber = 1
        ds.InstanceNumber = i + 1
        ds.Modality = "CT"
        ds.StudyDescription = "RadAI Synthetic CT (smoke test)"
        ds.SeriesDescription = "Axial Sphere"
        ds.AccessionNumber = "RADAI-SMOKE-001"
        ds.FrameOfReferenceUID = frame_of_reference_uid
        ds.PositionReferenceIndicator = ""
        ds.ImagePositionPatient = [0.0, 0.0, float(i)]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.SliceThickness = 1.0
        ds.SliceLocation = float(i)
        ds.PixelSpacing = [1.0, 1.0]

        # Pixel data
        ds.Rows = rows
        ds.Columns = cols
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1  # signed
        ds.RescaleIntercept = 0
        ds.RescaleSlope = 1
        ds.WindowCenter = 40
        ds.WindowWidth = 400
        ds.PixelData = slice_img.tobytes()

        ds.is_little_endian = True
        ds.is_implicit_VR = False
        ds.save_as(str(fp), write_like_original=False)
        files.append(fp)

    return files


# ─── Upload ──────────────────────────────────────────────────────────────────
def upload_file(client: httpx.Client, orthanc_url: str, auth: tuple[str, str], path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            data = f.read()
        r = client.post(
            f"{orthanc_url}/instances",
            content=data,
            headers={"Content-Type": "application/dicom"},
            auth=auth,
            timeout=30,
        )
        if r.status_code in (200, 201):
            return True
        fail(f"{path.name}: HTTP {r.status_code} {r.text[:120]}")
        return False
    except Exception as e:
        fail(f"{path.name}: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload DICOM files to Orthanc")
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a DICOM file or directory. Omit to use --synthetic.",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Generate and upload a small synthetic CT study",
    )
    parser.add_argument(
        "--tcia",
        action="store_true",
        help="Download a real lung CT from TCIA and upload it",
    )
    parser.add_argument(
        "--orthanc-url",
        default=os.environ.get("ORTHANC_URL", "https://localhost/orthanc"),
    )
    parser.add_argument("--user", default=os.environ.get("ORTHANC_USER", "orthanc"))
    parser.add_argument("--password", default=os.environ.get("ORTHANC_PASSWORD", "orthanc"))
    parser.add_argument("--synthetic-dir", default="./temp-synthetic-dicom")
    parser.add_argument("--tcia-dir", default="./real-ct-data")
    args = parser.parse_args()

    print(f"{C.B}== RadAI DICOM Upload =={C.E}")
    print(f"Target: {args.orthanc_url}")

    # Determine the file list
    if args.tcia:
        tcia_dir = Path(args.tcia_dir)
        existing = list(tcia_dir.glob("*.dcm")) + [
            f for f in tcia_dir.glob("*") if f.is_file() and f.suffix == ""
        ]
        if len(existing) < 10:
            print(f"Downloading real CT from TCIA to {tcia_dir} ...")
            try:
                from download_tcia_ct import find_and_download
                with httpx.Client(timeout=60) as dl_client:
                    existing = find_and_download(
                        dl_client, "NSCLC-Radiomics", "LUNG1-001", tcia_dir, 150
                    )
            except ImportError:
                fail("download_tcia_ct.py not found — run from RadAI/scripts/")
                return 1
        if not existing:
            fail("No DICOM files available")
            return 1
        files = existing
        ok(f"Using {len(files)} real CT DICOM files")
    elif args.synthetic or not args.path:
        print(f"Generating synthetic CT in {args.synthetic_dir} ...")
        files = generate_synthetic_ct(Path(args.synthetic_dir))
        ok(f"Generated {len(files)} synthetic DICOM slices")
    else:
        base = Path(args.path)
        if not base.exists():
            fail(f"Path not found: {base}")
            return 1
        files = list(iter_dicom_files(base))
        if not files:
            fail(f"No DICOM files found under {base}")
            return 1
        ok(f"Found {len(files)} DICOM file(s) in {base}")

    # Upload each file
    print(f"\nUploading to Orthanc ...")
    auth = (args.user, args.password)
    uploaded = 0
    with httpx.Client(verify=False) as client:
        for i, f in enumerate(files, 1):
            if upload_file(client, args.orthanc_url, auth, f):
                uploaded += 1
                if i % 10 == 0 or i == len(files):
                    print(f"  {i}/{len(files)} uploaded")

    if uploaded == len(files):
        ok(f"All {uploaded} instances uploaded successfully")
    else:
        warn(f"Uploaded {uploaded}/{len(files)} (see errors above)")

    # Verify via DICOMweb QIDO-RS
    print(f"\nVerifying via DICOMweb ...")
    try:
        with httpx.Client(verify=False) as client:
            r = client.get(
                f"{args.orthanc_url}/dicom-web/studies",
                auth=auth,
                timeout=10,
            )
            if r.status_code == 200:
                studies = r.json() if r.text else []
                ok(f"QIDO-RS reports {len(studies)} total studies in Orthanc")
            else:
                warn(f"QIDO-RS returned {r.status_code}")
    except Exception as e:
        warn(f"DICOMweb verification failed: {e}")

    return 0 if uploaded == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
