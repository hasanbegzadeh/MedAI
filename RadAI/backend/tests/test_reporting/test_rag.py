"""Tests for the RAG (Retrieval-Augmented Generation) clinical context system."""

from __future__ import annotations

import pytest

from app.reporting.rag import ClinicalRAG, CLINICAL_REFERENCES


class TestClinicalRAG:
    """Tests for ClinicalRAG retrieval and prompt building."""

    def setup_method(self):
        """Create a fresh RAG instance for each test."""
        self.rag = ClinicalRAG()

    @pytest.mark.asyncio
    async def test_retrieve_lung_nodule(self):
        """RAG retrieves Lung-RADS and Fleischner for lung nodule findings."""
        result = await self.rag.retrieve(
            findings_text="8mm solid nodule in the right upper lobe",
            modality="CT",
            body_part="chest",
        )

        assert len(result["references"]) > 0
        sources = [s["source"] for s in result["sources"]]
        # Should match Lung-RADS or Fleischner guidelines
        assert any("Lung-RADS" in s or "Fleischner" in s for s in sources)

    @pytest.mark.asyncio
    async def test_retrieve_liver_lesion(self):
        """RAG retrieves LI-RADS for liver lesion findings."""
        result = await self.rag.retrieve(
            findings_text="arterial enhancing liver mass with washout, possible HCC",
            modality="CT",
            body_part="liver",
        )

        assert len(result["references"]) > 0
        sources = [s["source"] for s in result["sources"]]
        assert any("LI-RADS" in s for s in sources)

    @pytest.mark.asyncio
    async def test_retrieve_no_match(self):
        """RAG returns empty when no references match."""
        result = await self.rag.retrieve(
            findings_text="normal study with no abnormalities",
            modality="PT",
            body_part="whole_body",
        )

        assert result["references"] == []
        assert result["context_text"] == ""
        assert result["sources"] == []

    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k(self):
        """RAG limits results to top_k."""
        result = await self.rag.retrieve(
            findings_text="nodule chest lung solid ground-glass",
            modality="CT",
            body_part="chest",
            top_k=1,
        )

        assert len(result["references"]) <= 1

    @pytest.mark.asyncio
    async def test_build_report_prompt_with_rag(self):
        """Build prompt includes clinical guidelines context."""
        prompt = await self.rag.build_report_prompt(
            findings_text="8mm solid nodule in RUL",
            modality="CT",
            body_part="chest",
            use_rag=True,
        )

        assert "CLINICAL GUIDELINES" in prompt
        assert "8mm solid nodule" in prompt
        assert "STRUCTURED FINDINGS" in prompt

    @pytest.mark.asyncio
    async def test_build_report_prompt_without_rag(self):
        """Build prompt without RAG returns standard prompt."""
        prompt = await self.rag.build_report_prompt(
            findings_text="Normal chest CT",
            use_rag=False,
        )

        assert "CLINICAL GUIDELINES" not in prompt
        assert "radiology assistant" in prompt.lower()
        assert "Normal chest CT" in prompt

    def test_add_custom_reference(self):
        """Custom references can be added to the database."""
        # Use a fresh RAG with a copy of references to avoid polluting shared state
        rag = ClinicalRAG(reference_db=list(CLINICAL_REFERENCES))
        initial_count = len(rag._references)
        rag.add_reference({
            "id": "custom-test",
            "content": "Test guideline content",
            "source": "Test Source",
            "keywords": ["test"],
        })
        assert len(rag._references) == initial_count + 1

    def test_add_reference_requires_keys(self):
        """Adding reference without required keys raises ValueError."""
        rag = ClinicalRAG(reference_db=[])
        with pytest.raises(ValueError, match="must have keys"):
            rag.add_reference({"id": "incomplete"})

    def test_keyword_extraction(self):
        """Keyword extraction removes stopwords and returns medical terms."""
        keywords = self.rag._extract_keywords("8mm solid nodule in the right upper lobe")
        assert "nodule" in keywords
        assert "solid" in keywords
        assert "the" not in keywords
        assert "in" not in keywords

    def test_embedded_references_count(self):
        """Verify all 10 clinical guidelines are embedded."""
        assert len(CLINICAL_REFERENCES) == 10

    def test_reference_structure(self):
        """All references have required fields."""
        for ref in CLINICAL_REFERENCES:
            assert "id" in ref
            assert "content" in ref
            assert "source" in ref
            assert "keywords" in ref
            assert len(ref["content"]) > 50  # Non-trivial content
