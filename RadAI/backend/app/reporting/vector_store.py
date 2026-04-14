"""RadAI — Vector store for semantic RAG retrieval.

Wraps ChromaDB (embedded, no external service) with sentence-transformer
embeddings for clinical guideline and prior report retrieval.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Lazy imports — ChromaDB and sentence-transformers are heavy
_chromadb = None
_collection = None


class VectorStore:
    """ChromaDB-backed vector store for clinical reference retrieval."""

    COLLECTION_GUIDELINES = "clinical_guidelines"
    COLLECTION_REPORTS = "prior_reports"

    def __init__(self, persist_dir: str, embedding_model: str = "all-MiniLM-L6-v2"):
        self._persist_dir = Path(persist_dir)
        self._embedding_model = embedding_model
        self._client = None
        self._ef = None  # embedding function
        self._guidelines_col = None
        self._reports_col = None

    def _ensure_client(self):
        """Lazy-init ChromaDB client and embedding function."""
        if self._client is not None:
            return

        import chromadb
        from chromadb.utils import embedding_functions

        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self._embedding_model,
        )

        self._guidelines_col = self._client.get_or_create_collection(
            name=self.COLLECTION_GUIDELINES,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._reports_col = self._client.get_or_create_collection(
            name=self.COLLECTION_REPORTS,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            "VectorStore initialized",
            persist_dir=str(self._persist_dir),
            guidelines_count=self._guidelines_col.count(),
            reports_count=self._reports_col.count(),
        )

    def index_guidelines(self, references: list[dict[str, Any]]) -> int:
        """Index clinical guidelines into the vector store.

        Idempotent: skips documents that already exist by ID.
        Returns count of newly added documents.
        """
        self._ensure_client()

        existing_ids = set(self._guidelines_col.get()["ids"])
        new_docs = [r for r in references if r["id"] not in existing_ids]

        if not new_docs:
            return 0

        self._guidelines_col.add(
            ids=[r["id"] for r in new_docs],
            documents=[r["content"] for r in new_docs],
            metadatas=[
                {
                    "source": r.get("source", ""),
                    "modality": r.get("modality", ""),
                    "body_part": r.get("body_part", ""),
                    "finding_types": ",".join(r.get("finding_types", [])),
                }
                for r in new_docs
            ],
        )

        logger.info("Indexed clinical guidelines", count=len(new_docs))
        return len(new_docs)

    def search_guidelines(
        self,
        query_text: str,
        top_k: int = 3,
        modality: str | None = None,
        body_part: str | None = None,
    ) -> list[dict]:
        """Semantic search over clinical guidelines.

        Returns list of dicts with: id, content, source, score, metadata.
        """
        self._ensure_client()

        where_filter = None
        conditions = []
        if modality:
            conditions.append({"modality": modality.upper()})
        if body_part:
            conditions.append({"body_part": body_part.lower()})

        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        try:
            results = self._guidelines_col.query(
                query_texts=[query_text],
                n_results=min(top_k, self._guidelines_col.count() or 1),
                where=where_filter if where_filter else None,
            )
        except Exception:
            # If filtered query fails (e.g., no matching metadata), try without filter
            results = self._guidelines_col.query(
                query_texts=[query_text],
                n_results=min(top_k, self._guidelines_col.count() or 1),
            )

        if not results["ids"] or not results["ids"][0]:
            return []

        output = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results.get("distances") else 0
            similarity = 1 - distance  # cosine distance to similarity

            output.append({
                "id": doc_id,
                "content": results["documents"][0][i],
                "source": results["metadatas"][0][i].get("source", ""),
                "score": round(similarity, 4),
                "metadata": results["metadatas"][0][i],
            })

        return output

    def add_prior_report(
        self,
        report_id: str,
        content_text: str,
        metadata: dict | None = None,
    ) -> None:
        """Index a finalized report for future comparison retrieval."""
        self._ensure_client()

        existing = set(self._reports_col.get()["ids"])
        if report_id in existing:
            return

        meta = metadata or {}
        self._reports_col.add(
            ids=[report_id],
            documents=[content_text],
            metadatas=[meta],
        )

        logger.info("Indexed prior report", report_id=report_id)

    def search_similar_reports(
        self,
        query_text: str,
        top_k: int = 3,
    ) -> list[dict]:
        """Find prior reports with similar findings for comparison language."""
        self._ensure_client()

        count = self._reports_col.count()
        if count == 0:
            return []

        results = self._reports_col.query(
            query_texts=[query_text],
            n_results=min(top_k, count),
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        output = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results.get("distances") else 0
            similarity = 1 - distance

            output.append({
                "report_id": doc_id,
                "content": results["documents"][0][i],
                "score": round(similarity, 4),
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
            })

        return output

    def reset_collection(self, collection_name: str) -> None:
        """Delete and recreate a collection."""
        self._ensure_client()
        self._client.delete_collection(collection_name)
        if collection_name == self.COLLECTION_GUIDELINES:
            self._guidelines_col = self._client.create_collection(
                name=collection_name,
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )
        elif collection_name == self.COLLECTION_REPORTS:
            self._reports_col = self._client.create_collection(
                name=collection_name,
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )


# ─── Singleton ───────────────────────────────────────────────────────────────
_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Return the process-wide VectorStore singleton."""
    global _vector_store
    if _vector_store is None:
        from app.config import get_settings
        settings = get_settings()
        _vector_store = VectorStore(
            persist_dir=getattr(settings, "vector_db_path", "./data/vectordb"),
            embedding_model=getattr(settings, "rag_embedding_model", "all-MiniLM-L6-v2"),
        )
    return _vector_store
