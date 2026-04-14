"""RadAI — Metadata Agent (KeyBERT) for clinical keyword extraction."""

import logging
import structlog
from typing import List

logger = structlog.get_logger(__name__)

# Lazy initialization to avoid slow startups unless used
_kw_model = None

def get_keybert_model():
    """Lazily load the KeyBERT model to save memory."""
    global _kw_model
    if _kw_model is None:
        try:
            from keybert import KeyBERT
            logger.info("Initializing KeyBERT model (all-MiniLM-L6-v2)")
            _kw_model = KeyBERT("all-MiniLM-L6-v2")
        except ImportError as exc:
            logger.error("Failed to import keybert. Please ensure it is installed.", exc_info=exc)
            raise
    return _kw_model

async def extract_keywords(text: str, top_n: int = 5) -> List[str]:
    """
    Extract key clinical terminology from unstructured text.
    
    Args:
        text: The unstructured clinical report.
        top_n: Number of keywords to return.
        
    Returns:
        List of prominent keywords/phrases extracted from the text.
    """
    if not text or not text.strip():
        return []
        
    try:
        kw_model = get_keybert_model()
        
        # Extract keywords with unigrams or bigrams
        keywords = kw_model.extract_keywords(
            text, 
            keyphrase_ngram_range=(1, 2), 
            stop_words='english', 
            top_n=top_n
        )
        
        # keybert returns list of tuples: [('keyword', score), ...]
        return [kw[0] for kw in keywords]
    except Exception as exc:
        logger.warning(f"Keyword extraction failed: {exc}")
        return []
