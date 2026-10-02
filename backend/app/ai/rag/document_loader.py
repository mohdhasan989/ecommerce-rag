"""Document loading and text extraction for RAG ingestion.

Supports PDF, TXT and Markdown. Each extracted unit is a LangChain ``Document``
so it flows straight into the chunker and on into the standard pipeline:

    file -> DocumentLoader -> text extraction -> chunker -> embedding -> Qdrant

No product or order data ever passes through here; that stays in MySQL.
"""
from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.documents import Document

from app.ai.config import get_ai_config
from app.ai.exceptions import DocumentLoadError

log = logging.getLogger("app.ai.loader")

__all__ = ["SUPPORTED_EXTENSIONS", "load_file", "load_directory", "infer_document_type"]

SUPPORTED_EXTENSIONS = {".pdf": "pdf", ".txt": "text", ".md": "markdown", ".markdown": "markdown"}


def infer_document_type(path: str | Path) -> str:
    return SUPPORTED_EXTENSIONS.get(Path(path).suffix.lower(), "unknown")


def _load_pdf(path: Path) -> list[Document]:
    from pypdf import PdfReader  # imported lazily; only needed for PDFs

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001 - pypdf raises many types
        log.warning("Failed to open PDF %s: %s", path.name, type(exc).__name__)
        raise DocumentLoadError(f"Could not read the PDF '{path.name}'.") from exc

    documents: list[Document] = []
    try:
        pages = reader.pages
    except Exception as exc:  # noqa: BLE001
        raise DocumentLoadError(f"Could not read the PDF '{path.name}'.") from exc

    for index, page in enumerate(pages, start=1):
        try:
            content = (page.extract_text() or "").strip()
        except Exception:  # noqa: BLE001 - a single bad page must not kill the file
            log.warning("Skipping unreadable page %d of %s", index, path.name)
            continue
        if content:
            # 1-based page number, matching what a reader sees in the document.
            documents.append(Document(page_content=content, metadata={"page": index}))
    if not documents:
        raise DocumentLoadError(
            f"No readable text found in '{path.name}'. Scanned PDFs are not supported."
        )
    return documents


def _load_text(path: Path) -> list[Document]:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            content = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise DocumentLoadError(f"Could not decode '{path.name}' as text.")

    content = content.strip()
    if not content:
        raise DocumentLoadError(f"'{path.name}' is empty.")
    return [Document(page_content=content, metadata={})]


def load_file(path: str | Path) -> list[Document]:
    """Load one file into ``Document`` objects carrying base metadata.

    Metadata attached here: ``source`` (file name), ``document_type``
    (pdf/text/markdown) and ``page`` where meaningful.
    """
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise DocumentLoadError(f"File '{file_path.name}' was not found.")

    kind = infer_document_type(file_path)
    if kind == "unknown":
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise DocumentLoadError(
            f"Unsupported file type '{file_path.suffix}'. Supported: {supported}."
        )

    documents = _load_pdf(file_path) if kind == "pdf" else _load_text(file_path)
    for document in documents:
        document.metadata.setdefault("source", file_path.name)
        document.metadata["document_type"] = kind
        document.metadata.setdefault("page", None)
    log.info("Loaded %s (%d unit(s)) from %s", file_path.name, len(documents), kind)
    return documents


def load_directory(path: str | Path, pattern: str = "**/*") -> list[Document]:
    """Load every supported document under ``path`` (recursively)."""
    root = Path(path)
    if not root.exists():
        raise DocumentLoadError(f"Directory '{root}' was not found.")
    if not root.is_dir():
        raise DocumentLoadError(f"'{root.name}' is not a directory.")

    documents: list[Document] = []
    skipped: list[str] = []
    for file_path in sorted(root.glob(pattern)):
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue
        if infer_document_type(file_path) == "unknown":
            skipped.append(file_path.name)
            continue
        documents.extend(load_file(file_path))

    if skipped:
        log.info("Skipped %d unsupported file(s): %s", len(skipped), ", ".join(skipped))
    if not documents:
        raise DocumentLoadError(f"No supported documents found in '{root.name}'.")
    return documents


def default_documents_dir() -> Path:
    """Resolved ``RAG_DOCUMENTS_DIR`` relative to the backend project root."""
    configured = get_ai_config().documents_dir
    candidate = Path(configured)
    if candidate.is_absolute():
        return candidate
    return Path(__file__).resolve().parents[3] / configured