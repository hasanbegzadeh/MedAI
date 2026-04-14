"""Tests for the multi-modality support registry."""

from __future__ import annotations

import pytest

from app.ai.modality_registry import (
    ModalityConfig,
    ModalityError,
    ModalityRegistry,
    ModalityType,
    get_modality_registry,
)


class TestModalityRegistry:
    """Tests for modality lookup and configuration."""

    def setup_method(self):
        self.registry = ModalityRegistry()

    def test_get_ct_modality(self):
        """CT modality is properly configured."""
        ct = self.registry.get_modality("CT")
        assert ct.name == "Computed Tomography"
        assert ct.tier == 1
        assert "totalsegmentator" in ct.ai_models
        assert "nodule_detection" in ct.ai_models

    def test_get_mri_modality(self):
        """MRI modality is properly configured."""
        mri = self.registry.get_modality("MRI")
        assert mri.name == "Magnetic Resonance Imaging"
        assert mri.tier == 2
        assert "brain" in mri.body_parts

    def test_xray_variants_map_correctly(self):
        """CR and DX DICOM codes both map to XRAY modality."""
        cr = self.registry.get_modality("CR")
        dx = self.registry.get_modality("DX")
        assert cr.name == dx.name
        assert "chexpert" in cr.ai_models

    def test_unsupported_modality_raises(self):
        """Unsupported modality raises ModalityError."""
        with pytest.raises(ModalityError, match="Unsupported modality"):
            self.registry.get_modality("UNKNOWN")

    def test_get_supported_modalities(self):
        """Returns all registered modality names."""
        modalities = self.registry.get_supported_modalities()
        assert "CT" in modalities
        assert "MRI" in modalities
        assert "XRAY" in modalities
        assert "US" in modalities
        assert "MG" in modalities

    def test_get_available_models_ct(self):
        """CT has multiple available AI models."""
        models = self.registry.get_available_models("CT")
        model_names = [m["name"] for m in models]
        assert "totalsegmentator" in model_names
        assert "nodule_detection" in model_names
        assert "nninteractive" in model_names
        assert "litemedsam" in model_names

    def test_model_info_structure(self):
        """Model info dicts contain required fields."""
        models = self.registry.get_available_models("CT")
        for model in models:
            assert "name" in model
            assert "description" in model
            assert "vram_gb" in model
            assert "tier" in model
            assert "status" in model

    def test_get_report_templates(self):
        """CT report templates include lung_rads."""
        templates = self.registry.get_report_templates("CT")
        assert "lung_rads" in templates
        assert "general_ct" in templates

    def test_is_supported(self):
        """is_supported returns correct values."""
        assert self.registry.is_supported("CT") is True
        assert self.registry.is_supported("MRI") is True
        assert self.registry.is_supported("FAKE") is False

    def test_recommend_template_chest_ct(self):
        """Recommends lung_rads for chest CT."""
        template = self.registry.recommend_template("CT", body_part="chest")
        assert template == "lung_rads"

    def test_recommend_template_brain_mri(self):
        """Recommends brain_mri for brain MRI."""
        template = self.registry.recommend_template("MRI", body_part="brain")
        assert template == "brain_mri"

    def test_recommend_template_default(self):
        """Returns first template when no body_part match."""
        template = self.registry.recommend_template("CT", body_part=None)
        assert template is not None
        assert isinstance(template, str)

    def test_singleton_pattern(self):
        """get_modality_registry returns same instance."""
        r1 = get_modality_registry()
        r2 = get_modality_registry()
        assert r1 is r2

    def test_modality_type_enum(self):
        """ModalityType enum has expected values."""
        assert ModalityType.CT.value == "CT"
        assert ModalityType.MR.value == "MR"
        assert ModalityType.US.value == "US"
        assert ModalityType.MG.value == "MG"
