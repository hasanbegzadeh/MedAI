"""Tests for DICOM converter module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pydicom
import pytest


class TestDICOMConverter:
    """Tests for DICOM to NIfTI conversion utilities."""

    def test_dicom_series_to_nifti_requires_valid_input(self):
        """Converter raises on invalid input directory."""
        from app.dicom.converter import dicom_series_to_nifti

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.nii.gz"

            # Empty directory should raise
            with pytest.raises(Exception):
                dicom_series_to_nifti(Path(tmpdir) / "nonexistent", output_path)

    def test_dicom_anonymizer_preserves_structure(self):
        """Anonymizer removes patient info but keeps study structure."""
        import pydicom
        from pydicom.dataset import Dataset
        from app.dicom.anonymizer import DICOMAnonymizer

        # Create a minimal DICOM-like dataset
        ds = Dataset()
        ds.PatientName = "Test^Patient"
        ds.PatientID = "12345"
        ds.StudyInstanceUID = "1.2.3.4.5"
        ds.SeriesInstanceUID = "1.2.3.4.6"
        ds.SOPInstanceUID = "1.2.3.4.7"
        ds.Modality = "CT"

        # Anonymize
        anonymizer = DICOMAnonymizer()
        anon_ds = anonymizer._anonymize_dataset(ds)

        # Patient name should be replaced with ANONYMIZED
        assert str(anon_ds.PatientName) == "ANONYMIZED"
        # Study UID should be replaced (new generated UID)
        assert anon_ds.get("StudyInstanceUID") is not None
        assert str(anon_ds.StudyInstanceUID) != "1.2.3.4.5"
        # Modality should be preserved
        assert anon_ds.Modality == "CT"

    def test_seg_export_creates_valid_structure(self):
        """DICOM-SEG export creates proper file structure."""
        pytest.importorskip("highdicom")
        from app.dicom.seg_export import create_seg_dataset

        # Create synthetic segmentation mask
        mask = np.zeros((10, 64, 64), dtype=np.uint8)
        mask[3:7, 20:44, 20:44] = 1  # Simple box "segmentation"

        # Create minimal source image reference
        source_ds = pydicom.Dataset()
        source_ds.SOPClassUID = pydicom.uid.CTImageStorage
        source_ds.SOPInstanceUID = pydicom.uid.generate_uid()
        source_ds.SeriesInstanceUID = pydicom.uid.generate_uid()
        source_ds.StudyInstanceUID = pydicom.uid.generate_uid()

        # Should create SEG dataset
        seg_ds = create_seg_dataset(mask, source_ds, segment_label="Test Structure")

        assert seg_ds is not None
        assert hasattr(seg_ds, "SOPClassUID")
