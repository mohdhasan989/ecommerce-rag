"""RAG ingestion and retrieval pipeline."""

from app.ai.rag.chunker import get_splitter, split_documents
from app.ai.rag.document_loader import (
    SUPPORTED_EXTENSIONS,
    load_directory,
    load_file,
)
from app.ai.rag.ingestion import IngestionResult, ingest_documents, ingest_paths
from app.ai.rag.retriever import RetrievedChunk, RetrievalResult, retrieve

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "load_file",
    "load_directory",
    "get_splitter",
    "split_documents",
    "ingest_paths",
    "ingest_documents",
    "IngestionResult",
    "retrieve",
    "RetrievalResult",
    "RetrievedChunk",
]