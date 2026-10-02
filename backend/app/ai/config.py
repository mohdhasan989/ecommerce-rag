"""Centralised AI/RAG configuration.

The single source of truth for every Milestone 2 environment variable is
``app.config.Settings`` (one ``.env``, one loader). This module derives a
read-only, typed view over those values and never touches ``os.environ`` or
re-reads ``.env``, so there is exactly one configuration system in the project.

Nothing in this module (or anywhere under ``app.ai``) is allowed to log or
return a secret; use :func:`AIConfig.status` for redacted health output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from app.config import settings

__all__ = ["AIConfig", "ai_config", "get_ai_config", "reset_ai_config_cache"]

# Which settings gate which capability. Values are the *names* of the required
# settings; used to produce actionable "what do I need to set" errors.
REQUIRED_FOR = {
    "groq": ("GROQ_API_KEY",),
    "qdrant": ("QDRANT_URL", "QDRANT_API_KEY"),
    "embeddings": ("HF_API_KEY",),
    "rag": ("GROQ_API_KEY", "HF_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"),
}


@dataclass(frozen=True)
class AIConfig:
    """Immutable snapshot of every AI-related setting.

    Every field has a default so tests (and future call sites) can build a
    narrow config without restating 20 values. Production always uses
    :func:`get_ai_config`, which reads ``app.config.Settings``.
    """

    # --- Groq LLM ---
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_temperature: float = 0.2
    groq_max_tokens: int = 800

    # --- Hugging Face embeddings ---
    hf_api_key: str = ""
    hf_embedding_model: str = "BAAI/bge-small-en-v1.5"
    hf_api_url: str = "https://router.huggingface.co/hf-inference"
    hf_embed_batch_size: int = 32

    # --- Qdrant Cloud ---
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "ecommerce_knowledge"

    # --- RAG pipeline ---
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 5
    min_score: float = 0.30
    documents_dir: str = "documents"
    max_upload_mb: int = 10

    # --- Router / chat ---
    router_confidence_threshold: float = 0.80
    max_message_length: int = 1000

    # Derived / non-secret extras used by health reporting.
    supported_document_types: tuple[str, ...] = field(
        default=("pdf", "txt", "markdown"), repr=False
    )

    # ---------------- capability checks ----------------

    @staticmethod
    def _present(value: str) -> bool:
        return bool(value and value.strip())

    def missing(self, capability: str) -> list[str]:
        """Return the env var names still unset for ``capability``."""
        required = REQUIRED_FOR.get(capability)
        if required is None:
            raise KeyError(f"Unknown AI capability '{capability}'")
        lookup = {
            "GROQ_API_KEY": self.groq_api_key,
            "HF_API_KEY": self.hf_api_key,
            "QDRANT_URL": self.qdrant_url,
            "QDRANT_API_KEY": self.qdrant_api_key,
        }
        return [name for name in required if not self._present(lookup[name])]

    def is_configured(self, capability: str) -> bool:
        return not self.missing(capability)

    def status(self) -> dict[str, str]:
        """Redacted capability report. Never contains key material."""
        return {
            "groq": "configured" if self.is_configured("groq") else "missing_api_key",
            "embeddings": (
                "configured" if self.is_configured("embeddings") else "missing_api_key"
            ),
            "qdrant": "configured" if self.is_configured("qdrant") else "missing_configuration",
            "model": self.groq_model,
            "embedding_model": self.hf_embedding_model,
            "collection": self.qdrant_collection,
        }


def _build() -> AIConfig:
    return AIConfig(
        groq_api_key=settings.GROQ_API_KEY,
        groq_model=settings.GROQ_MODEL,
        groq_temperature=settings.GROQ_TEMPERATURE,
        groq_max_tokens=settings.GROQ_MAX_TOKENS,
        hf_api_key=settings.HF_API_KEY,
        hf_embedding_model=settings.HF_EMBEDDING_MODEL,
        hf_api_url=settings.HF_API_URL.rstrip("/"),
        hf_embed_batch_size=settings.HF_EMBED_BATCH_SIZE,
        qdrant_url=settings.QDRANT_URL,
        qdrant_api_key=settings.QDRANT_API_KEY,
        qdrant_collection=settings.QDRANT_COLLECTION,
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        top_k=settings.RAG_TOP_K,
        min_score=settings.RAG_MIN_SCORE,
        documents_dir=settings.RAG_DOCUMENTS_DIR,
        max_upload_mb=settings.RAG_MAX_UPLOAD_MB,
        router_confidence_threshold=settings.ROUTER_CONFIDENCE_THRESHOLD,
        max_message_length=settings.CHAT_MAX_MESSAGE_LENGTH,
    )


@lru_cache(maxsize=1)
def get_ai_config() -> AIConfig:
    return _build()


def reset_ai_config_cache() -> None:
    """Drop the cached snapshot (used by tests that patch settings)."""
    get_ai_config.cache_clear()


# Module-level convenience handle, mirroring ``app.config.settings``.
ai_config = get_ai_config()