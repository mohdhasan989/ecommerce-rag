"""Hugging Face embedding service.

Implements a real LangChain ``Embeddings`` interface so it plugs into any
LangChain retriever/chain, while talking to the Hugging Face Inference API over
HTTPS (no torch / sentence-transformers install required).

Two operations are exposed, as required:
  * ``embed_documents`` -- for ingestion
  * ``embed_query``     -- for retrieval

The vector dimension is **discovered at runtime**, never hardcoded: we ask the
model for a real embedding and read its length, with a cheap fallback to the
model's published ``hidden_size``. That keeps the Qdrant collection correct if
``HF_EMBEDDING_MODEL`` is ever swapped.
"""
from __future__ import annotations

import logging
import re
import threading
from functools import lru_cache

import httpx
from langchain_core.embeddings import Embeddings

from app.ai.config import AIConfig, get_ai_config
from app.ai.exceptions import ConfigurationError, EmbeddingError

log = logging.getLogger("app.ai.embeddings")

__all__ = ["HFEmbeddings", "get_embeddings", "embedding_dimension", "reset_embedding_cache"]

# Probe string is only used to measure dimensionality; content is irrelevant.
_DIM_PROBE = "dimension probe"
_lock = threading.Lock()


class HFEmbeddings(Embeddings):
    """LangChain-compatible embeddings backed by the HF Inference API."""

    def __init__(self, config: AIConfig | None = None, client: httpx.Client | None = None):
        self._config = config or get_ai_config()
        self._client = client
        self._dimension: int | None = None

    # ---------------- configuration ----------------

    # ------------------------------------------------------------------
    # Hugging Face retired the original Inference host, api-inference.
    # huggingface.co (it no longer resolves), and moved model serving behind the
    # router. The legacy host is listed here only so that existing .env files
    # pointing at it are mapped onto the router instead of failing with a DNS
    # error.
    # ------------------------------------------------------------------
    _LEGACY_HOST = "api-inference.huggingface.co"
    _ROUTER_BASE = "https://router.huggingface.co/hf-inference"

    @property
    def model(self) -> str:
        return self._config.hf_embedding_model

    @property
    def _endpoint(self) -> str:
        base = self._config.hf_api_url.rstrip("/")
        if base.endswith(self._LEGACY_HOST):
            log.warning(
                "HF_API_URL=%s is retired and no longer resolves; using %s "
                "instead. Update HF_API_URL in backend/.env.",
                base,
                self._ROUTER_BASE,
            )
            base = self._ROUTER_BASE
        return f"{base}/models/{self.model}"

    def _require_key(self) -> str:
        if not self._config.hf_api_key.strip():
            raise ConfigurationError(self._config.missing("embeddings"), "embeddings")
        return self._config.hf_api_key

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    # ---------------- core API ----------------

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunks for ingestion."""
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single user question for retrieval."""
        vectors = self._embed([text])
        if not vectors:
            raise EmbeddingError("The embedding model returned no vector for this query.")
        return vectors[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        key = self._require_key()
        payload = {"inputs": list(texts), "options": {"wait_for_model": True}}
        headers = {"Authorization": f"Bearer {key}"}
        try:
            response = self._http().post(
                self._endpoint, json=payload, headers=headers, timeout=120.0
            )
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                "Could not reach the embedding provider. Please try again."
            ) from exc
        except OSError as exc:
            # DNS/TCP/TLS failures below httpx's own exception hierarchy must
            # still surface as a clean provider error, never a raw 500.
            raise EmbeddingError(
                "Could not reach the embedding provider. Please try again."
            ) from exc

        if response.status_code >= 400:
            raise EmbeddingError(self._explain(response))

        try:
            body = response.json()
        except ValueError as exc:  # non-JSON error page
            raise EmbeddingError(
                "The embedding provider returned an unreadable response."
            ) from exc
        vectors = self._normalise(body)
        if not vectors:
            raise EmbeddingError("The embedding model returned no vectors.")
        if self._dimension is None:
            self._dimension = len(vectors[0])
        return vectors

    @staticmethod
    def _normalise(body: object) -> list[list[float]]:
        """HF returns either [[floats]] (batch) or [floats] (single)."""
        if not isinstance(body, list) or not body:
            return []
        if isinstance(body[0], list):
            return [[float(x) for x in vec] for vec in body if isinstance(vec, list)]
        return [[float(x) for x in body]]

    def _redact(self, text: str) -> str:
        """Strip key material from anything we surface or log."""
        key = self._config.hf_api_key
        if key:
            text = text.replace(key, "hf_REDACTED")
        return re.sub(r"hf_[A-Za-z0-9]{10,}", "hf_REDACTED", text)

    def _provider_detail(self, response: httpx.Response) -> str:
        """Best-effort extraction of the provider's own error text.

        Returning only a generic sentence makes provider-side problems (unsupported
        model, gated repo, cold start) impossible to diagnose from the logs, so the
        upstream `error`/`message` field is preserved - redacted and truncated.
        """
        text = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                text = str(body.get("error") or body.get("message") or "")
        except ValueError:
            text = response.text or ""
        return self._redact(text.strip())[:200]

    def _explain(self, response: httpx.Response) -> str:
        status = response.status_code
        detail = self._provider_detail(response)
        log.error(
            "huggingface: HTTP %s %s | endpoint=%s | provider said: %s",
            status, response.reason_phrase, self._endpoint, detail or "<no detail>",
        )
        suffix = f" Provider said: {detail}" if detail else ""
        if status in (401, 403):
            return "The embedding provider rejected the credentials. Check HF_API_KEY." + suffix
        if status == 404:
            return f"Embedding model '{self.model}' was not found or is not available." + suffix
        if status == 429:
            return "The embedding provider is rate limited. Please retry shortly." + suffix
        if status == 503:
            return "The embedding model is loading. Please retry in a moment." + suffix
        return "The embedding provider could not process this request." + suffix

    # ---------------- dimension discovery ----------------

    def dimension(self) -> int:
        """Resolve the true vector size at runtime (cached)."""
        if self._dimension is not None:
            return self._dimension
        with _lock:
            if self._dimension is not None:
                return self._dimension
            # Authoritative: embed a probe and measure.
            try:
                self._embed([_DIM_PROBE])
                if self._dimension:
                    return self._dimension
            except (EmbeddingError, ConfigurationError) as exc:
                log.warning("Probe embedding failed (%s); trying model metadata", exc.code)
            # Fallback: published hidden_size.
            size = self._hidden_size_from_metadata()
            if not size:
                raise EmbeddingError(
                    "Could not determine the vector dimension for this embedding model."
                )
            self._dimension = size
            return size

    def _hidden_size_from_metadata(self) -> int | None:
        """Read the model's published hidden size as a dimension fallback.

        The /api/models response omits ``hidden_size`` for BERT-style encoders
        (it only carries architectures/model_type/tokenizer_config), so the
        repo's own ``config.json`` is consulted as well. That file answers 307 to
        the CDN, hence follow_redirects.
        """
        for url in (
            f"https://huggingface.co/{self.model}/resolve/main/config.json",
            f"https://huggingface.co/api/models/{self.model}",
        ):
            try:
                response = httpx.get(url, timeout=20.0, follow_redirects=True)
                if response.status_code >= 400:
                    continue
                body = response.json()
                if not isinstance(body, dict):
                    continue
                value = body.get("hidden_size") or (body.get("config") or {}).get(
                    "hidden_size"
                )
                if value:
                    return int(value)
            except (httpx.HTTPError, TypeError, ValueError, AttributeError):
                continue
        return None


@lru_cache(maxsize=1)
def get_embeddings() -> HFEmbeddings:
    """Shared embedding service instance."""
    return HFEmbeddings()


def embedding_dimension() -> int:
    """Vector size for the configured embedding model (never hardcoded)."""
    return get_embeddings().dimension()


def reset_embedding_cache() -> None:
    get_embeddings.cache_clear()