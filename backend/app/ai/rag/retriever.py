"""RAG retrieval: question -> embedding -> Qdrant similarity search -> top-K chunks.

Returns a normalised list so the context builder never has to know where the
chunks came from:

    [{"text": "...", "score": 0.91, "metadata": {"source": ..., "page": ...}}, ...]
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from app.ai.config import AIConfig, get_ai_config
from app.ai.embeddings.hf_embeddings import get_embeddings
from app.ai.vectorstore.qdrant_client import get_vector_store

log = logging.getLogger("app.ai.retriever")

__all__ = ["RetrievedChunk", "RetrievalResult", "retrieve", "retrieve_with_scores"]

# Metadata keys kept in the payload for display/debugging.
_KEEP_KEYS = ("source", "page", "document_type", "chunk_index", "start_index")


@dataclass
class RetrievedChunk:
    text: str
    score: float | None = None
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    query: str = ""
    top_k: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "top_k": self.top_k,
            "count": len(self.chunks),
            "chunks": [chunk.as_dict() for chunk in self.chunks],
        }


def _clean_metadata(payload: dict) -> dict:
    return {key: payload[key] for key in _KEEP_KEYS if key in payload}


def retrieve(
    question: str,
    *,
    top_k: int | None = None,
    config: AIConfig | None = None,
) -> RetrievalResult:
    """Run the retrieval half of the RAG pipeline for one question."""
    config = config or get_ai_config()
    question = (question or "").strip()
    limit = int(top_k or config.top_k)
    result = RetrievalResult(query=question, top_k=limit)
    if not question or limit <= 0:
        return result

    vector = get_embeddings().embed_query(question)
    raw = get_vector_store().search(
        vector=vector, top_k=limit, min_score=config.min_score
    )
    result.chunks = [
        RetrievedChunk(
            text=hit.get("text") or "",
            score=hit.get("score"),
            metadata=_clean_metadata(hit.get("metadata") or {}),
        )
        for hit in raw
        if (hit.get("text") or "").strip()
    ]
    log.info("Retrieved %d chunk(s) for %r", len(result.chunks), question[:60])
    return result


def retrieve_with_scores(question: str, **kwargs) -> list[dict]:
    """Convenience wrapper returning plain dicts."""
    return [chunk.as_dict() for chunk in retrieve(question, **kwargs).chunks]