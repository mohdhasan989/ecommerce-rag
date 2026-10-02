"""AI/RAG error taxonomy.

Every failure mode listed in the Milestone 2 spec maps to one exception here.
Each exception carries a safe, user-facing message and an HTTP status; the
router turns them into the project's existing ``{"error": {...}}`` envelope.

Rules enforced by this module:
  * never carry an API key, URL credential or raw provider payload upward;
  * provider responses are summarised, not echoed, to the client.
"""
from __future__ import annotations

import logging

log = logging.getLogger("app.ai")

__all__ = [
    "AIError",
    "ConfigurationError",
    "EmbeddingError",
    "LLMError",
    "VectorStoreError",
    "DocumentLoadError",
]


class AIError(Exception):
    """Base class. ``message`` is always safe to return to a client."""

    status_code = 503
    code = "AI_SERVICE_ERROR"

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class ConfigurationError(AIError):
    """A required environment variable is missing or unusable."""

    status_code = 503
    code = "AI_NOT_CONFIGURED"

    def __init__(
        self,
        missing: list[str] | str,
        capability: str,
        message: str | None = None,
    ):
        # ``missing`` is normally the list of env var NAMES still absent. A bare
        # string is accepted too, for cases where the variable is present but
        # unusable (e.g. the provider rejected it).
        if isinstance(missing, str):
            missing = [missing]
        self.missing = list(missing)
        self.capability = capability
        detail = (
            f"Set the following in backend/.env to enable {capability}: "
            + ", ".join(self.missing)
            if self.missing
            else None
        )
        super().__init__(
            message or f"The {capability} feature is not configured yet.",
            detail=detail,
        )


class EmbeddingError(AIError):
    """The embedding provider refused or failed to produce vectors."""

    status_code = 502
    code = "EMBEDDING_ERROR"


class LLMError(AIError):
    """The chat-completion provider refused or failed."""

    status_code = 502
    code = "LLM_ERROR"


class VectorStoreError(AIError):
    """Qdrant Cloud was unreachable or rejected a request."""

    status_code = 502
    code = "VECTOR_STORE_ERROR"


class DocumentLoadError(AIError):
    """A document could not be read or is an unsupported type."""

    status_code = 400
    code = "DOCUMENT_ERROR"


def safe_provider_error(exc: Exception, provider: str) -> str:
    """Build a log-safe one-liner. Strips anything resembling a secret."""
    raw = f"{type(exc).__name__}: {exc}"
    for marker in ("api_key", "apikey", "Authorization", "Bearer", "token"):
        idx = raw.lower().find(marker.lower())
        if idx != -1:
            raw = raw[:idx] + "[redacted]"
    return f"{provider}: {raw[:300]}"