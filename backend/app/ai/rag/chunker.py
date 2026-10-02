"""Configurable chunking.

Kept out of the API route on purpose. ``CHUNK_SIZE`` / ``CHUNK_OVERLAP`` come from
configuration, and every chunk keeps the metadata of the document it came from
(``source``, ``page``, ``document_type``) plus its own ``chunk_index``.
"""
from __future__ import annotations

import logging

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ai.config import AIConfig, get_ai_config
from app.ai.exceptions import ConfigurationError

log = logging.getLogger("app.ai.chunker")

__all__ = ["get_splitter", "split_documents", "chunk_count"]


def _validate(config: AIConfig) -> None:
    if config.chunk_size <= 0:
        raise ConfigurationError(["RAG_CHUNK_SIZE"], "rag")
    if config.chunk_overlap < 0 or config.chunk_overlap >= config.chunk_size:
        raise ConfigurationError(["RAG_CHUNK_OVERLAP"], "rag")


def get_splitter(config: AIConfig | None = None) -> RecursiveCharacterTextSplitter:
    """Splitter built from configured chunk size/overlap."""
    config = config or get_ai_config()
    _validate(config)
    return RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        length_function=len,
        keep_separator=True,
        add_start_index=True,
        strip_whitespace=True,
        # Respect natural structure before falling back to hard character cuts.
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def split_documents(
    documents: list[Document], config: AIConfig | None = None
) -> list[Document]:
    """Split into chunks, preserving and enriching metadata."""
    if not documents:
        return []
    splitter = get_splitter(config)
    chunks = splitter.split_documents(documents)

    for index, chunk in enumerate(chunks):
        # start_index is set by add_start_index; carry it under a stable name.
        start = chunk.metadata.pop("start_index", None)
        if start is not None:
            chunk.metadata["start_index"] = int(start)
        chunk.metadata["chunk_index"] = index

    log.info("Split %d document unit(s) into %d chunk(s)", len(documents), len(chunks))
    return chunks


def chunk_count(documents: list[Document], config: AIConfig | None = None) -> int:
    return len(split_documents(documents, config))