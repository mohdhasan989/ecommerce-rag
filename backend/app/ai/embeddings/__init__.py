"""Hugging Face embedding service (documents + queries)."""

from app.ai.embeddings.hf_embeddings import (
    HFEmbeddings,
    embedding_dimension,
    get_embeddings,
    reset_embedding_cache,
)

__all__ = [
    "HFEmbeddings",
    "get_embeddings",
    "embedding_dimension",
    "reset_embedding_cache",
]