"""RadAI — RAG (Retrieval-Augmented Generation) for clinical context.

Retrieves relevant clinical references, prior studies, and imaging
guidelines to enhance AI-generated radiology reports with evidence-based
context.

Architecture:
1. Extract keywords from current study findings
2. Search clinical reference database for similar cases
3. Inject relevant guidelines (e.g., Lung-RADS management recommendations)
4. Pass findings + clinical context to report generation LLM

Usage::

    rag = ClinicalRAG()
    context = await rag.retrieve(findings_text="8mm solid nodule in RUL")
    report = await generate_report(findings, clinical_context=context)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)


# ─── Clinical Reference Database ──────────────────────────────────────────────
# Embedded clinical guidelines for common radiology findings.
# In production, this would be a vector database (Chroma, Weaviate, Qdrant)
# or connection to PubMed/RadLex.

CLINICAL_REFERENCES: list[dict[str, Any]] = [
    # Lung-RADS guidelines
    {
        "id": "lung-rads-v2022",
        "modality": "CT",
        "body_part": "chest",
        "finding_types": ["nodule"],
        "keywords": ["nodule", "lung", "solid", "ground-glass", "part-solid"],
        "content": (
            "Lung-RADS v2022 Management Guidelines:\n"
            "- Category 1 (Negative): No nodules >6mm. Annual screening recommended.\n"
            "- Category 2 (Benign): Nodules <6mm or clearly benign. Annual screening.\n"
            "- Category 3 (Probably Benign): Solid nodules 6-8mm. Follow-up CT at 6-12 months.\n"
            "- Category 4A: Solid nodules 8-15mm or new 6-8mm. Follow-up CT at 3 months.\n"
            "- Category 4B: Solid nodules >15mm or spiculated. PET/CT, tissue sampling, or 3-month follow-up.\n"
            "- Category 4X: Add specifier for additional findings. 3-month follow-up or tissue sampling.\n"
            "New nodules or growing nodules on serial CT require more aggressive management."
        ),
        "source": "ACR Lung-RADS v2022",
    },
    {
        "id": "fleiischner-2017",
        "modality": "CT",
        "body_part": "chest",
        "finding_types": ["nodule", "ground_glass"],
        "keywords": ["incidental", "nodule", "fleiischner", "solitary"],
        "content": (
            "Fleischner Society 2017 Guidelines for Incidental Pulmonary Nodules:\n"
            "- Single solid nodule <6mm: No routine follow-up (high-risk: optional 12mo CT).\n"
            "- Single solid nodule 6-8mm: CT at 6-12mo, then 18-24mo (high-risk).\n"
            "- Single solid nodule >8mm: CT at 3mo, PET/CT, or tissue sampling.\n"
            "- Multiple solid nodules <6mm: No routine follow-up (high-risk: 12mo CT).\n"
            "- Multiple solid nodules, smallest <6mm: CT at 3-6mo, then 18-24mo.\n"
            "- Ground-glass nodules <6mm: No follow-up needed.\n"
            "- Ground-glass nodules >=6mm: CT at 6-12mo, then every 2 years for 5 years."
        ),
        "source": "Fleischner Society 2017",
    },
    # BI-RADS guidelines
    {
        "id": "bi-rads-2013",
        "modality": "MRI",
        "body_part": "breast",
        "finding_types": ["mass", "lesion"],
        "keywords": ["breast", "mass", "lesion", "enhancement", "BI-RADS"],
        "content": (
            "BI-RADS Assessment Categories (2013):\n"
            "- Category 0: Incomplete — Need additional imaging evaluation.\n"
            "- Category 1: Negative — Routine screening.\n"
            "- Category 2: Benign — Routine screening.\n"
            "- Category 3: Probably Benign — Short-interval follow-up (6mo).\n"
            "- Category 4A: Low suspicion for malignancy — Tissue diagnosis.\n"
            "- Category 4B: Moderate suspicion — Tissue diagnosis.\n"
            "- Category 4C: High suspicion — Tissue diagnosis.\n"
            "- Category 5: Highly suggestive of malignancy — Appropriate action.\n"
            "- Category 6: Known biopsy-proven malignancy."
        ),
        "source": "ACR BI-RADS 2013",
    },
    # LI-RADS guidelines
    {
        "id": "li-rads-v2018",
        "modality": "CT",
        "body_part": "liver",
        "finding_types": ["lesion", "mass"],
        "keywords": ["liver", "hepatocellular", "HCC", "LI-RADS", "arterial"],
        "content": (
            "LI-RADS v2018 for Hepatocellular Carcinoma:\n"
            "- LR-1: Definitely benign — No action needed.\n"
            "- LR-2: Probably benign — Continue routine surveillance.\n"
            "- LR-3: Intermediate probability — Short-interval follow-up (3-6mo).\n"
            "- LR-4: Probably HCC — Multidisciplinary discussion, biopsy, or treatment.\n"
            "- LR-5: Definitely HCC — Treatment without biopsy.\n"
            "- LR-M: Probably or definitely malignant, not specific for HCC.\n"
            "- LR-TIV: Tumor in vein — Aggressive management.\n"
            "Key imaging features: arterial phase hyperenhancement (APHE), "
            "nonperipheral washout, enhancing capsule, threshold growth."
        ),
        "source": "ACR LI-RADS v2018",
    },
    # Incidental findings
    {
        "id": "incidental-thyroid",
        "modality": "CT",
        "body_part": "chest",
        "finding_types": ["thyroid"],
        "keywords": ["thyroid", "nodule", "incidental", "neck"],
        "content": (
            "Incidental Thyroid Nodules on CT:\n"
            "- Nodules <1cm: No further evaluation needed in most cases.\n"
            "- Nodules >=1cm: Recommend thyroid ultrasound for characterization.\n"
            "- Nodules with suspicious features (calcifications, extrathyroidal extension): "
            "Urgent ultrasound and possible FNA biopsy.\n"
            "- Incidental thyroid uptake on PET/CT: Ultrasound recommended."
        ),
        "source": "ACR Incidental Findings Committee",
    },
    {
        "id": "incidental-adrenal",
        "modality": "CT",
        "body_part": "abdomen",
        "finding_types": ["adrenal"],
        "keywords": ["adrenal", "incidental", "adenoma", "nodule", "HU"],
        "content": (
            "Incidental Adrenal Lesions on CT:\n"
            "- Lesions <1cm with unenhanced HU <=10: Benign adenoma, no follow-up.\n"
            "- Lesions >=1cm with unenhanced HU <=10: Likely adenoma, consider follow-up if history of malignancy.\n"
            "- Lesions with unenhanced HU >10: Further characterization with adrenal protocol CT or MRI.\n"
            "- Lesions >4cm: Surgical consultation recommended regardless of imaging features."
        ),
        "source": "ACR Incidental Findings Committee",
    },
    # MRI spine guidelines
    {
        "id": "spine-degenerative",
        "modality": "MRI",
        "body_part": "spine",
        "finding_types": ["disc", "stenosis", "degeneration"],
        "keywords": ["disc", "herniation", "stenosis", "degeneration", "spine", "nerve"],
        "content": (
            "Degenerative Spine Disease Reporting Guidelines:\n"
            "- Disc bulge: Broad-based extension beyond disc space, often asymptomatic.\n"
            "- Disc protrusion: Focal extension, may cause nerve root impingement.\n"
            "- Disc extrusion: Narrower base than dome, higher risk of radiculopathy.\n"
            "- Spinal stenosis: Central canal narrowing. Mild (>10mm), Moderate (7-10mm), Severe (<7mm).\n"
            "- Foraminal stenosis: Nerve root compression graded by loss of perineural fat.\n"
            "- Correlate imaging findings with clinical symptoms for management recommendations."
        ),
        "source": "NASS Imaging Guidelines",
    },
    # Brain MRI guidelines
    {
        "id": "brain-mri-lesions",
        "modality": "MRI",
        "body_part": "brain",
        "finding_types": ["lesion", "mass"],
        "keywords": ["brain", "lesion", "mass", "enhancement", "edema", "midline"],
        "content": (
            "Brain MRI Lesion Reporting Guidelines:\n"
            "- Document location: lobe, deep gray matter, brainstem, cerebellum.\n"
            "- Size: measure in 3 dimensions (AP x transverse x CC).\n"
            "- Enhancement pattern: none, solid, ring, heterogeneous.\n"
            "- Mass effect: midline shift (mm), ventricular compression, herniation.\n"
            "- Edema: none, mild, moderate, severe.\n"
            "- Differential diagnosis: primary tumor, metastasis, abscess, demyelination, infarct.\n"
            "- Recommend contrast-enhanced sequences if not already performed."
        ),
        "source": "ACR Appropriateness Criteria",
    },
    # Chest X-ray guidelines
    {
        "id": "chest-xray-findings",
        "modality": "CT",
        "body_part": "chest",
        "finding_types": ["consolidation", "effusion", "pneumothorax", "cardiac"],
        "keywords": ["chest", "x-ray", "radiograph", "consolidation", "effusion", "pneumothorax", "cardiomegaly"],
        "content": (
            "Chest Radiograph Reporting Guidelines:\n"
            "- Technical factors: PA/AP, lateral, portable, inspiration quality.\n"
            "- Lungs: consolidation, nodules, masses, interstitial pattern, pneumothorax.\n"
            "- Pleura: effusion (small/moderate/large), thickening, pneumothorax.\n"
            "- Heart: size (CTR >0.5 = cardiomegaly), contour, pericardial effusion.\n"
            "- Mediastinum: width, hilar enlargement, lymphadenopathy.\n"
            "- Bones: fractures, lytic/blastic lesions, degenerative changes.\n"
            "- Lines/tubes: ETT, NG tube, central lines, chest tubes."
        ),
        "source": "Royal College of Radiologists",
    },
    # Ultrasound guidelines
    {
        "id": "thyroid-ultrasound-ti-rads",
        "modality": "US",
        "body_part": "thyroid",
        "finding_types": ["nodule", "thyroid"],
        "keywords": ["thyroid", "ultrasound", "TI-RADS", "echogenicity", "microcalcification"],
        "content": (
            "ACR TI-RADS Thyroid Nodule Classification:\n"
            "- Composition: cystic (0), spongiform (0), mixed (1), solid (2).\n"
            "- Echogenicity: anechoic (0), hyperechoic (1), isoechoic (2), hypoechoic (2), very hypoechoic (3).\n"
            "- Shape: wider-than-tall (0), taller-than-wide (3).\n"
            "- Margin: smooth (0), ill-defined (0), lobulated (2), extrathyroidal extension (3).\n"
            "- Echogenic foci: none (0), large comet-tail (0), macrocalcifications (1), peripheral (2), microcalcifications (3).\n"
            "- TR1 (0 points): Benign, no FNA. TR2 (2 points): Not suspicious, no FNA.\n"
            "- TR3 (3 points): Mildly suspicious, FNA if >=2.5cm.\n"
            "- TR4 (4-6 points): Moderately suspicious, FNA if >=1.5cm.\n"
            "- TR5 (>=7 points): Highly suspicious, FNA if >=1cm."
        ),
        "source": "ACR TI-RADS 2017",
    },
]


class RAGError(Exception):
    """Raised when RAG retrieval fails."""


class ClinicalRAG:
    """Retrieval-Augmented Generation for clinical context.

    Provides evidence-based clinical guidelines to enhance AI-generated
    radiology reports with appropriate management recommendations.

    Supports two backends:
    - "keyword": Keyword overlap scoring (default, no extra deps)
    - "vector": ChromaDB + sentence-transformers semantic search
    """

    def __init__(
        self,
        reference_db: list[dict] | None = None,
        rag_backend: str | None = None,
    ):
        """Initialize RAG system.

        Args:
            reference_db: Optional custom reference database.
                         Uses embedded defaults if None.
            rag_backend: "keyword" or "vector". If None, reads from settings.
        """
        self._references = reference_db or CLINICAL_REFERENCES
        self._settings = get_settings()
        self._backend = rag_backend or getattr(self._settings, "rag_backend", "keyword")
        self._vector_store = None

        if self._backend == "vector":
            self._init_vector_backend()

    def _init_vector_backend(self):
        """Initialize the vector store and index guidelines."""
        try:
            from app.reporting.vector_store import get_vector_store
            self._vector_store = get_vector_store()
            self._vector_store.index_guidelines(self._references)
            logger.info("Vector RAG backend initialized")
        except Exception as exc:
            logger.warning(
                "Vector backend init failed, falling back to keyword",
                error=str(exc),
            )
            self._backend = "keyword"
            self._vector_store = None

    async def retrieve(
        self,
        findings_text: str,
        modality: str | None = None,
        body_part: str | None = None,
        top_k: int = 3,
    ) -> dict[str, Any]:
        """Retrieve relevant clinical references for the given findings.

        Routes to keyword or vector backend based on configuration.
        """
        if self._backend == "vector" and self._vector_store is not None:
            return await self._retrieve_vector(findings_text, modality, body_part, top_k)
        return await self._retrieve_keyword(findings_text, modality, body_part, top_k)

    async def _retrieve_vector(
        self,
        findings_text: str,
        modality: str | None,
        body_part: str | None,
        top_k: int,
    ) -> dict[str, Any]:
        """Semantic vector search over clinical guidelines."""
        results = self._vector_store.search_guidelines(
            query_text=findings_text,
            top_k=top_k,
            modality=modality,
            body_part=body_part,
        )

        if not results:
            return {"references": [], "context_text": "", "sources": []}

        context_parts = []
        sources = []
        references = []
        for r in results:
            context_parts.append(f"[{r['source']}]\n{r['content']}")
            sources.append({
                "id": r["id"],
                "source": r["source"],
                "relevance_score": r["score"],
            })
            references.append((r["score"], r))

        context_text = "\n\n".join(context_parts)
        logger.info(
            "Vector RAG retrieval complete",
            matches=len(results),
            sources=[s["source"] for s in sources],
        )

        return {
            "references": references,
            "context_text": context_text,
            "sources": sources,
        }

    async def _retrieve_keyword(
        self,
        findings_text: str,
        modality: str | None,
        body_part: str | None,
        top_k: int,
    ) -> dict[str, Any]:
        """Original keyword-based retrieval."""
        keywords = self._extract_keywords(findings_text)

        scored_refs = []
        for ref in self._references:
            score = self._score_reference(ref, keywords, modality, body_part)
            if score > 0:
                scored_refs.append((score, ref))

        scored_refs.sort(key=lambda x: x[0], reverse=True)
        top_refs = scored_refs[:top_k]

        if not top_refs:
            logger.info(
                "No clinical references matched",
                keywords=keywords,
                modality=modality,
                body_part=body_part,
            )
            return {"references": [], "context_text": "", "sources": []}

        context_parts = []
        sources = []
        for score, ref in top_refs:
            context_parts.append(
                f"[{ref['source']}]\n{ref['content']}"
            )
            sources.append({
                "id": ref["id"],
                "source": ref["source"],
                "relevance_score": score,
            })

        context_text = "\n\n".join(context_parts)

        logger.info(
            "RAG retrieval complete",
            matches=len(top_refs),
            sources=[s["source"] for s in sources],
        )

        return {
            "references": top_refs,
            "context_text": context_text,
            "sources": sources,
        }

    async def retrieve_prior_reports(
        self,
        findings_text: str,
        top_k: int = 3,
    ) -> list[dict]:
        """Retrieve similar prior reports for comparison language.

        Only available with vector backend.
        """
        if self._backend != "vector" or self._vector_store is None:
            return []
        return self._vector_store.search_similar_reports(findings_text, top_k)

    def index_report(
        self,
        report_id: str,
        content_text: str,
        metadata: dict | None = None,
    ) -> None:
        """Index a finalized report for future comparison retrieval.

        Only available with vector backend.
        """
        if self._backend != "vector" or self._vector_store is None:
            return
        self._vector_store.add_prior_report(report_id, content_text, metadata)

    async def build_report_prompt(
        self,
        findings_text: str,
        findings_dicts: list[dict] | None = None,
        modality: str | None = None,
        body_part: str | None = None,
        use_rag: bool = True,
    ) -> str:
        """Build an enhanced report generation prompt with RAG context.

        Args:
            findings_text: Structured findings as plain text.
            findings_dicts: Optional list of finding dicts for keyword extraction.
            modality: Imaging modality.
            body_part: Anatomical region.
            use_rag: Whether to include RAG context.

        Returns:
            Enhanced prompt with clinical context injected.
        """
        if not use_rag:
            # Fall back to standard prompt without RAG
            return (
                "You are a radiology assistant. Rewrite the following structured findings "
                "into professional radiology report prose. "
                "PRESERVE ALL measurements, values, and anatomical details EXACTLY. "
                "DO NOT invent, add, or omit any findings.\n\n"
                f"Structured Findings:\n{findings_text}"
            )

        # Retrieve clinical context
        rag_result = await self.retrieve(findings_text, modality, body_part)

        if not rag_result["context_text"]:
            # No references found, fall back to standard
            return (
                "You are a radiology assistant. Rewrite the following structured findings "
                "into professional radiology report prose. "
                "PRESERVE ALL measurements, values, and anatomical details EXACTLY. "
                "DO NOT invent, add, or omit any findings.\n\n"
                f"Structured Findings:\n{findings_text}"
            )

        # Build enhanced prompt with RAG context
        prompt = (
            "You are a board-certified radiologist assistant. "
            "Rewrite the following structured findings into a professional radiology report.\n\n"
            "CLINICAL GUIDELINES (use these for management recommendations):\n"
            f"{rag_result['context_text']}\n\n"
            "STRUCTURED FINDINGS (preserve ALL details exactly):\n"
            f"{findings_text}\n\n"
            "INSTRUCTIONS:\n"
            "1. Write findings in standard radiology prose format.\n"
            "2. Preserve every measurement, HU value, and anatomical detail.\n"
            "3. Add evidence-based management recommendations from the clinical guidelines above.\n"
            "4. Do NOT add findings not present in the structured data.\n"
            "5. Use standard radiology terminology.\n"
            "6. If Lung-RADS or BI-RADS category is implied, state it explicitly.\n"
        )

        return prompt

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract search keywords from findings text.

        Simple tokenization + medical term filtering.
        In production, use a medical NLP (cTAKES, CLAMP, or MedSpaCy).
        """
        # Common medical stop words to exclude
        medical_stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "need", "dare", "ought", "used", "to", "of", "in", "for",
            "on", "with", "at", "by", "from", "as", "into", "through",
            "during", "before", "after", "above", "below", "between",
            "out", "off", "over", "under", "again", "further", "then",
            "once", "and", "but", "or", "nor", "not", "so", "yet",
            "both", "either", "neither", "each", "every", "all",
            "any", "few", "more", "most", "other", "some", "such",
            "no", "only", "own", "same", "than", "too", "very",
            "just", "don", "now", "cm", "mm", "ml", "hu",
            "measured", "approximately", "noted", "seen", "demonstrates",
            "shows", "reveals", "compatible", "consistent", "suggestive",
            "likely", "possible", "probable", "without", "within",
            "right", "left", "bilateral", "upper", "lower", "middle",
        }

        # Simple tokenization
        import re
        tokens = re.findall(r'[a-zA-Z]+(?:-[a-zA-Z]+)*', text.lower())

        # Filter stopwords and short tokens
        keywords = [t for t in tokens if t not in medical_stopwords and len(t) > 2]

        # Also extract bigrams and trigrams that appear in text
        ngrams = []
        words = text.lower().split()
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if any(kw in bigram for kw in keywords):
                ngrams.append(bigram)

        return list(set(keywords + ngrams))

    def _score_reference(
        self,
        ref: dict,
        keywords: list[str],
        modality: str | None,
        body_part: str | None,
    ) -> float:
        """Score a reference by relevance to the findings.

        Scoring:
        - Keyword overlap: 1 point per matching keyword
        - Modality match: 2 points
        - Body part match: 2 points
        - Finding type match: 3 points per match
        """
        score = 0.0
        ref_keywords = {kw.lower() for kw in ref.get("keywords", [])}
        ref_finding_types = set(ref.get("finding_types", []))

        # Keyword overlap
        for kw in keywords:
            if kw in ref_keywords:
                score += 1.0

        # Modality match
        if modality and ref.get("modality", "").lower() == modality.lower():
            score += 2.0

        # Body part match
        if body_part and ref.get("body_part", "").lower() == body_part.lower():
            score += 2.0

        # Finding type match (stronger signal)
        for ft in ref_finding_types:
            if ft.lower() in " ".join(keywords).lower():
                score += 3.0

        return score

    def add_reference(self, reference: dict) -> None:
        """Add a custom clinical reference to the database.

        Args:
            reference: Dict with keys: id, modality, body_part,
                      finding_types, keywords, content, source.
        """
        required_keys = {"id", "content", "source"}
        if not required_keys.issubset(reference.keys()):
            raise ValueError(f"Reference must have keys: {required_keys}")
        self._references.append(reference)
        logger.info("Added clinical reference", id=reference["id"])

    def load_references_from_file(self, filepath: str | Path) -> None:
        """Load additional references from a JSON file.

        Args:
            filepath: Path to JSON file with list of reference dicts.
        """
        filepath = Path(filepath)
        with open(filepath, "r") as f:
            refs = json.load(f)
        for ref in refs:
            self.add_reference(ref)
        logger.info("Loaded references from file", path=str(filepath), count=len(refs))


# ─── Singleton ────────────────────────────────────────────────────────────────
_rag: ClinicalRAG | None = None


def get_clinical_rag() -> ClinicalRAG:
    """Return the process-wide ClinicalRAG singleton."""
    global _rag
    if _rag is None:
        _rag = ClinicalRAG()
    return _rag
