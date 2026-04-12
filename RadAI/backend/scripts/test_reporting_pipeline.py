"""Smoke test for Phase 2 reporting pipeline.

Tests:
1. Template engine renders Lung-RADS report
2. DICOM-SR creation from report text
3. PDF export from report text
"""
import sys
sys.path.insert(0, "/app")

from app.reporting.engine import get_template_engine, build_lung_rads_context
from app.reporting.dicom_sr import create_dicom_sr_text, save_dicom_sr
from app.reporting.pdf_export import generate_pdf_report
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
import tempfile
import os

print("=== Phase 2 Reporting Pipeline Smoke Test ===\n")

# ── 1. Template Engine ───────────────────────────────────────────────────────
print("1. Testing template engine...")
engine = get_template_engine()
templates = engine.list_templates()
print(f"   Available templates: {templates}")
assert "lung_rads.j2" in templates, "lung_rads.j2 template missing"
assert "general_ct.j2" in templates, "general_ct.j2 template missing"

# Build Lung-RADS context with sample findings
findings = [
    {
        "finding_type": "nodule",
        "location": "Right Upper Lobe",
        "description": "Solid pulmonary nodule identified in the right upper lobe.",
        "measurements": {"longest_diameter_mm": 6, "volume_mm3": 113.1, "mean_hu": -45},
    },
    {
        "finding_type": "nodule",
        "location": "Left Lower Lobe",
        "description": "Small ground-glass nodule in the left lower lobe.",
        "measurements": {"longest_diameter_mm": 4, "volume_mm3": 33.5, "mean_hu": -600},
    },
]

context = build_lung_rads_context(
    findings=findings,
    nodule_summary=[
        {"nodule_id": "NOD-R001", "location": "Right Upper Lobe", "diameter_mm": 6, "characteristics": "solid"},
        {"nodule_id": "NOD-L002", "location": "Left Lower Lobe", "diameter_mm": 4, "characteristics": "ground-glass"},
    ],
    lung_rads_category="Lung-RADS 3",
    lung_rads_description="Probably benign — short-term follow-up recommended",
    clinical_indication="Lung cancer screening, 30 pack-year smoking history",
)

report_text = engine.render("lung_rads.j2", context)
print(f"   Lung-RADS report generated: {len(report_text)} characters")
assert "Lung-RADS 3" in report_text, f"Lung-RADS category missing from report. Got: {report_text[:500]}"
assert "Right Upper Lobe" in report_text, "Finding location missing"
print("   ✅ Template engine PASSED\n")

# ── 2. DICOM-SR ─────────────────────────────────────────────────────────────
print("2. Testing DICOM-SR creation...")

# Create a minimal DICOM dataset to serve as source image
file_meta = Dataset()
file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
file_meta.MediaStorageSOPInstanceUID = generate_uid()
file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

source_ds = FileDataset("test.dcm", {}, file_meta=file_meta, preamble=b"\0" * 128)
source_ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
source_ds.SOPInstanceUID = generate_uid()
source_ds.StudyInstanceUID = generate_uid()
source_ds.PatientName = "TEST^PATIENT"
source_ds.PatientID = "SMOKE-001"

sr = create_dicom_sr_text(
    report_text=report_text,
    source_images=[source_ds],
    title="CT Chest Lung-RADS Report",
    author="Test Radiologist",
    classification="Lung-RADS 3",
    template_name="lung_rads.j2",
)

assert sr.Modality == "SR", f"Expected SR modality, got {sr.Modality}"
assert sr.SeriesNumber == 900
assert len(sr.ContentSequence) >= 3, f"Expected ≥3 content items, got {len(sr.ContentSequence)}"

# Save and verify
with tempfile.TemporaryDirectory() as tmpdir:
    sr_path = save_dicom_sr(sr, os.path.join(tmpdir, "report_sr.dcm"))
    assert sr_path.exists(), "DICOM-SR file not written"

    # Re-read and verify
    sr_read = pydicom.dcmread(str(sr_path))
    assert sr_read.Modality == "SR"
    assert sr_read.SeriesDescription == "RadAI Report: CT Chest Lung-RADS Report"

print(f"   DICOM-SR created: Modality={sr.Modality}, {len(sr.ContentSequence)} content items")
print("   ✅ DICOM-SR PASSED\n")

# ── 3. PDF Export ────────────────────────────────────────────────────────────
print("3. Testing PDF export...")

with tempfile.TemporaryDirectory() as tmpdir:
    pdf_path = generate_pdf_report(
        report_text=report_text,
        output_path=os.path.join(tmpdir, "report.pdf"),
        patient_name="TEST^PATIENT",
        patient_id="SMOKE-001",
        study_date="2026-04-11",
        referring_physician="Referring MD",
        radiologist="Test Radiologist",
        classification="Lung-RADS 3",
        template_name="lung_rads.j2",
    )

    assert pdf_path.exists(), "PDF file not written"
    pdf_size_kb = pdf_path.stat().st_size / 1024
    print(f"   PDF generated: {pdf_size_kb:.1f} KB")
    assert pdf_size_kb > 3, f"PDF too small ({pdf_size_kb:.1f} KB) — likely empty"

print("   ✅ PDF export PASSED\n")

# ── Summary ──────────────────────────────────────────────────────────────────
print("=" * 50)
print("All Phase 2 reporting pipeline tests PASSED ✅")
print(f"  - Template engine: 2 templates, {len(report_text)} char report")
print(f"  - DICOM-SR: {len(sr.ContentSequence)} content items")
print(f"  - PDF: {pdf_size_kb:.1f} KB")
