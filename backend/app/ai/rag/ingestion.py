"""Ingestion pipeline: documents -> chunks -> embeddings -> Qdrant Cloud.

    Documents -> Document Loader -> Text Extraction -> Chunking
             -> Embedding Model -> Qdrant

Run directly to index the documents directory:

    python -m app.ai.rag.ingestion
    python -m app.ai.rag.ingestion --path documents --no-replace
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document

from app.ai.config import AIConfig, get_ai_config
from app.ai.embeddings.hf_embeddings import get_embeddings
from app.ai.rag.chunker import split_documents
from app.ai.rag.document_loader import default_documents_dir, load_directory, load_file
from app.ai.vectorstore.qdrant_client import get_vector_store

log = logging.getLogger("app.ai.ingestion")

__all__ = ["IngestionResult", "build_points", "ingest_documents", "ingest_paths", "main"]


@dataclass
class IngestionResult:
    files: int = 0
    units: int = 0
    chunks: int = 0
    upserted: int = 0
    vector_size: int = 0
    collection: str = ""
    sources: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "files": self.files,
            "units": self.units,
            "chunks": self.chunks,
            "upserted": self.upserted,
            "vector_size": self.vector_size,
            "collection": self.collection,
            "sources": sorted(self.sources),
        }


def build_points(chunks: list[Document]) -> list[dict]:
    """Embed chunks and shape them into Qdrant points.

    Each point carries: vector, chunk text, metadata and a deterministic unique
    ID derived from ``source`` + ``page`` + ``chunk_index`` so re-ingesting the
    same content does not duplicate vectors.
    """
    if not chunks:
        return []
    embeddings = get_embeddings()
    vectors = embeddings.embed_documents([chunk.page_content for chunk in chunks])

    points: list[dict] = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        metadata = {
            key: value for key, value in chunk.metadata.items() if value is not None
        }
        source = str(metadata.get("source") or "unknown")
        page = metadata.get("page")
        chunk_index = metadata.get("chunk_index", index)
        # Stable, collision-resistant, Qdrant-valid (uuid5) point id.
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}|{page}|{chunk_index}"))
        points.append(
            {
                "id": point_id,
                "vector": vector,
                "text": chunk.page_content,
                "metadata": metadata,
            }
        )
    return points


def ingest_documents(
    documents: list[Document],
    *,
    config: AIConfig | None = None,
    replace: bool = True,
) -> IngestionResult:
    config = config or get_ai_config()
    store = get_vector_store()
    embeddings = get_embeddings()

    # Dimension is measured from the model, never assumed.
    vector_size = embeddings.dimension()
    store.ensure_collection(vector_size)

    result = IngestionResult(
        units=len(documents),
        vector_size=vector_size,
        collection=store.collection_name,
    )
    for document in documents:
        source = document.metadata.get("source")
        if source:
            result.sources.append(str(source))

    chunks = split_documents(documents, config)
    result.chunks = len(chunks)

    if replace:
        for source in dict.fromkeys(result.sources):
            # Re-ingesting a file must replace, not duplicate, its old chunks.
            store.delete_by_source(source)

    points = build_points(chunks)
    result.upserted = store.upsert(points)
    result.files = len(dict.fromkeys(result.sources))
    log.info("Ingested %s", result.as_dict())
    return result


def ingest_paths(
    paths: list[str | Path] | None = None,
    *,
    config: AIConfig | None = None,
    replace: bool = True,
) -> IngestionResult:
    """Ingest explicit files and/or directories (defaults to documents dir)."""
    documents: list[Document] = []
    for raw in paths or [default_documents_dir()]:
        path = Path(raw)
        documents.extend(load_file(path) if path.is_file() else load_directory(path))
    return ingest_documents(documents, config=config, replace=replace)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest documents into Qdrant Cloud.")
    parser.add_argument("--path", action="append", dest="paths",
                        help="File or directory (repeatable). Defaults to RAG_DOCUMENTS_DIR.")
    parser.add_argument("--no-replace", action="store_true",
                        help="Keep existing chunks instead of replacing per source file.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        result = ingest_paths(args.paths, replace=not args.no_replace)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        log.error("Ingestion failed: %s", exc)
        return 1
    print(f"Ingestion complete: {result.as_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())