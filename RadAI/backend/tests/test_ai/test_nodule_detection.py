"""Tests for nodule detection algorithm."""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.nodule_detection import detect_nodules, NoduleCandidate


class TestNoduleDetection:
    """Tests for lung nodule detection heuristic."""

    def test_detect_nodules_empty_volume(self):
        """Empty CT volume returns no candidates."""
        ct_volume = np.zeros((10, 64, 64), dtype=np.float32)
        lung_mask = np.zeros((10, 64, 64), dtype=np.int32)
        spacing = (1.5, 1.0, 1.0)

        candidates = detect_nodules(ct_volume, lung_mask, spacing)

        assert len(candidates) == 0

    def test_detect_nodules_with_synthetic_nodule(self):
        """Synthetic spherical nodule is detected."""
        # Create a CT volume with a synthetic nodule (high density sphere)
        ct_volume = np.full((20, 128, 128), -800, dtype=np.float32)  # Air-filled lung
        lung_mask = np.ones((20, 128, 128), dtype=np.int32)  # All lung

        # Add a spherical nodule (soft tissue density)
        center = (10, 64, 64)
        radius = 4  # 4 voxels
        z, y, x = np.ogrid[:20, :128, :128]
        dist = np.sqrt((z - center[0]) ** 2 + (y - center[1]) ** 2 + (x - center[2]) ** 2)
        ct_volume[dist <= radius] = 50  # Soft tissue HU

        spacing = (1.5, 1.0, 1.0)

        candidates = detect_nodules(ct_volume, lung_mask, spacing)

        # Should detect at least one candidate
        assert len(candidates) >= 1

    def test_nodule_candidate_structure(self):
        """NoduleCandidate has expected attributes."""
        candidate = NoduleCandidate(
            nodule_id="test-001",
            location="Right upper lobe",
            laterality="right",
            lobe="upper",
            centroid=(10.0, 64.0, 64.0),
            diameter_mm=8.5,
            volume_mm3=250.0,
            mean_hu=-450,
            max_hu=50,
            min_hu=-700,
            confidence=0.85,
        )

        assert candidate.nodule_id == "test-001"
        assert candidate.diameter_mm == 8.5
        assert candidate.confidence == 0.85
        assert candidate.mean_hu == -450
        assert candidate.centroid == (10.0, 64.0, 64.0)
        assert candidate.max_hu == 50
        assert candidate.min_hu == -700

    def test_detect_nodules_respects_mask(self):
        """Only detects nodules within lung mask."""
        ct_volume = np.full((10, 64, 64), -800, dtype=np.float32)
        lung_mask = np.zeros((10, 64, 64), dtype=np.int32)  # No lung mask

        # Add nodule outside mask
        ct_volume[5, 32, 32] = 50

        spacing = (1.5, 1.0, 1.0)

        candidates = detect_nodules(ct_volume, lung_mask, spacing)

        # Should find nothing since lung mask is empty
        assert len(candidates) == 0
