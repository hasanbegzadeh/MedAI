#!/usr/bin/env python3
"""Verify Phase 3 completion: Cloud Integration + RAG + Multi-modality.

Tests:
1. Cloud GPU client initialization
2. DICOM anonymization pipeline
3. RAG clinical reference retrieval
4. Multi-modality registry
5. API endpoint availability

Usage:
    python scripts/verify_phase_3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def verify_cloud_gpu_client() -> bool:
    """Verify cloud GPU client module loads correctly."""
    print("  [1/5] Checking cloud GPU client…")
    try:
        from app.cloud.gpu_client import CloudGPUClient, CloudGPUError, get_cloud_gpu_client

        client = CloudGPUClient()
        assert hasattr(client, "run_totalsegmentator")
        assert hasattr(client, "test_connection")
        assert not client._is_configured()  # Should be unconfigured by default

        # Test singleton
        singleton = get_cloud_gpu_client()
        assert singleton is not None

        print("  ✓ Cloud GPU client verified")
        return True
    except Exception as exc:
        print(f"  ✗ Cloud GPU client failed: {exc}")
        return False


def verify_anonymizer() -> bool:
    """Verify DICOM anonymizer module loads and functions."""
    print("  [2/5] Checking DICOM anonymizer…")
    try:
        from app.dicom.anonymizer import DICOMAnonymizer, AnonymizationError, create_anonymized_copy

        anonymizer = DICOMAnonymizer()
        assert hasattr(anonymizer, "anonymize_file")
        assert hasattr(anonymizer, "anonymize_directory")

        print("  ✓ DICOM anonymizer verified")
        return True
    except Exception as exc:
        print(f"  ✗ DICOM anonymizer failed: {exc}")
        return False


def verify_rag_system() -> bool:
    """Verify RAG clinical reference retrieval."""
    print("  [3/5] Checking RAG system…")
    try:
        import asyncio
        from app.reporting.rag import ClinicalRAG, get_clinical_rag

        rag = ClinicalRAG()

        # Test retrieval synchronously
        result = asyncio.get_event_loop().run_until_complete(
            rag.retrieve(
                findings_text="8mm solid nodule in right upper lobe",
                modality="CT",
                body_part="chest",
            )
        )

        assert "references" in result
        assert "context_text" in result
        assert "sources" in result
        assert len(result["references"]) > 0  # Should match Lung-RADS

        # Test singleton
        singleton = get_clinical_rag()
        assert singleton is not None

        print(f"  ✓ RAG system verified ({len(result['references'])} references matched)")
        return True
    except Exception as exc:
        print(f"  ✗ RAG system failed: {exc}")
        return False


def verify_modality_registry() -> bool:
    """Verify multi-modality registry."""
    print("  [4/5] Checking modality registry…")
    try:
        from app.ai.modality_registry import (
            ModalityRegistry,
            ModalityConfig,
            ModalityError,
            get_modality_registry,
            ModalityType,
        )

        registry = ModalityRegistry()

        # Test supported modalities
        supported = registry.get_supported_modalities()
        assert "CT" in supported
        assert "MRI" in supported
        assert "XRAY" in supported
        assert "US" in supported
        assert "MG" in supported

        # Test modality lookup
        ct = registry.get_modality("CT")
        assert ct.name == "Computed Tomography"
        assert len(ct.ai_models) > 0

        mri = registry.get_modality("MR")
        assert mri.name == "Magnetic Resonance Imaging"

        xray = registry.get_modality("DX")
        assert xray.name == "Digital Radiography (X-ray)"

        # Test model availability
        ct_models = registry.get_available_models("CT")
        assert len(ct_models) > 0
        assert any(m["name"] == "totalsegmentator" for m in ct_models)

        # Test template recommendation
        template = registry.recommend_template("CT", "chest")
        assert template in ("lung_rads", "general_ct")

        # Test singleton
        singleton = get_modality_registry()
        assert singleton is not None

        print(f"  ✓ Modality registry verified ({len(supported)} modalities)")
        return True
    except Exception as exc:
        print(f"  ✗ Modality registry failed: {exc}")
        return False


def verify_api_endpoints() -> bool:
    """Verify new API endpoints are registered."""
    print("  [5/5] Checking API endpoints…")
    try:
        from app.api.ai import router as ai_router
        from app.api.reports import router as reports_router

        # Check AI routes
        ai_routes = [route.path for route in ai_router.routes]
        assert "/modalities" in ai_routes
        assert "/modalities/{dicom_code}/models" in ai_routes
        assert "/studies/{study_id}/recommend-ai" in ai_routes

        # Check report routes
        report_routes = [route.path for route in reports_router.routes]
        assert "/rag/retrieve" in report_routes

        print("  ✓ API endpoints verified")
        return True
    except Exception as exc:
        print(f"  ✗ API endpoint check failed: {exc}")
        return False


def main() -> int:
    print("=" * 60)
    print("  Phase 3 Verification: Cloud + RAG + Multi-modality")
    print("=" * 60)

    checks = [
        verify_cloud_gpu_client,
        verify_anonymizer,
        verify_rag_system,
        verify_modality_registry,
        verify_api_endpoints,
    ]

    results = [check() for check in checks]
    passed = sum(results)
    total = len(results)

    print()
    print("-" * 60)
    print(f"  Results: {passed}/{total} checks passed")
    print("-" * 60)

    if passed == total:
        print("\n✓ Phase 3 verification complete. All systems operational.")
        return 0
    else:
        print(f"\n⚠ {total - passed} check(s) failed. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
