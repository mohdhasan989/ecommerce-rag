"""Qdrant Cloud vector store service.

Uses the hosted Qdrant Cloud REST/gRPC API via ``qdrant-client``. There is no
local Qdrant, no Docker and no vector data in MySQL -- MySQL keeps products and
orders only.

Capabilities:
  1. connect to Qdrant Cloud
  2. check whether the collection exists
  3. create the collection when missing (with a *measured* vector size)
  4. keep the payload indexes required by filtered deletes/searches correct
  5. upsert document vectors
  6. similarity search
  7. return chunks + metadata
"""
from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.ai.config import AIConfig, get_ai_config
from app.ai.exceptions import ConfigurationError, VectorStoreError, safe_provider_error

log = logging.getLogger("app.ai.qdrant")

__all__ = ["QdrantVectorStore", "get_vector_store", "reset_vector_store_cache"]

# Payload fields this store filters on, and the index each one requires.
# Qdrant refuses any filtered delete/search against an unindexed field with
# HTTP 400 "Index required but not found for <field>", which is what broke
# delete_by_source() during ingestion on a collection that existed but had no
# payload indexes at all.
INDEXED_PAYLOAD_FIELDS: dict[str, qmodels.PayloadSchemaType] = {
    "source": qmodels.PayloadSchemaType.KEYWORD,
}


class QdrantVectorStore:
    def __init__(self, config: AIConfig | None = None, client: QdrantClient | None = None):
        self._config = config or get_ai_config()
        self._client = client
        self._ensured = False

    # ---------------- configuration ----------------

    @property
    def collection_name(self) -> str:
        return self._config.qdrant_collection

    def _require_config(self) -> None:
        missing = self._config.missing("qdrant")
        if missing:
            raise ConfigurationError(missing, "qdrant")

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._require_config()
            try:
                self._client = QdrantClient(
                    url=self._config.qdrant_url,
                    api_key=self._config.qdrant_api_key,
                    timeout=30,
                )
            except Exception as exc:  # noqa: BLE001 - provider raises many types
                log.error(safe_provider_error(exc, "qdrant"))
                raise VectorStoreError(
                    "Could not connect to the vector store. Please try again."
                ) from exc
        return self._client

    # ---------------- connectivity ----------------

    def ping(self) -> bool:
        """Cheap round-trip used by the health endpoint. Never raises."""
        try:
            self.client.get_collections()
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning(safe_provider_error(exc, "qdrant.ping"))
            return False

    def collection_exists(self) -> bool:
        try:
            return bool(self.client.collection_exists(self.collection_name))
        except Exception as exc:  # noqa: BLE001
            log.error(safe_provider_error(exc, "qdrant.collection_exists"))
            raise VectorStoreError("Could not reach the vector store.") from exc

    @staticmethod
    def _index_kind_matches(info: Any, kind: qmodels.PayloadSchemaType) -> bool:
        """Compare an existing index type defensively.

        ``data_type`` is usually a ``PayloadSchemaType`` member but a plain
        string ("keyword") is accepted too, so normalise before comparing.
        """
        existing = getattr(info, "data_type", info)
        return getattr(existing, "value", existing) == kind.value

    def _ensure_payload_indexes(self, client: QdrantClient) -> None:
        """Make sure every payload field we filter on is indexed.

        Runs for new *and* pre-existing collections. Existing indexes of the
        right type are left alone, so this is idempotent and safe to call on
        every ingestion.
        """
        try:
            schema = client.get_collection(self.collection_name).payload_schema or {}
        except Exception as exc:  # noqa: BLE001
            log.error(safe_provider_error(exc, "qdrant.get_collection"))
            raise VectorStoreError(
                "Could not inspect the vector store collection."
            ) from exc

        for field, kind in INDEXED_PAYLOAD_FIELDS.items():
            existing = schema.get(field)
            if existing is not None and self._index_kind_matches(existing, kind):
                log.debug("payload index already present: %s (%s)", field, kind.value)
                continue
            if existing is not None:
                log.info(
                    "payload field '%s' is indexed as %s, expected %s; (re)creating",
                    field,
                    getattr(existing, "data_type", "unknown"),
                    kind.value,
                )
            try:
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=kind,
                    wait=True,
                )
            except Exception as exc:  # noqa: BLE001
                log.error(safe_provider_error(exc, "qdrant.create_payload_index"))
                raise VectorStoreError(
                    "Could not create the payload indexes the vector store needs."
                ) from exc
            log.info("Created %s payload index on '%s'", kind.value, field)

    def ensure_collection(self, vector_size: int) -> None:
        """Create the collection if needed and keep its payload indexes correct.

        Idempotent. An existing collection is never recreated or re-parameterised
        -- its vectors are left untouched -- but its payload indexes are still
        inspected and repaired, because Qdrant rejects filtered deletes on
        unindexed fields.
        """
        if self._ensured:
            return
        client = self.client
        try:
            if client.collection_exists(self.collection_name):
                log.debug(
                    "Qdrant collection '%s' already exists; keeping it as-is",
                    self.collection_name,
                )
            else:
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=int(vector_size), distance=qmodels.Distance.COSINE
                    ),
                )
                log.info(
                    "Created Qdrant collection '%s' (size=%d)", self.collection_name, vector_size
                )
        except Exception as exc:  # noqa: BLE001
            log.error(safe_provider_error(exc, "qdrant.create_collection"))
            raise VectorStoreError(
                "Could not prepare the vector store collection."
            ) from exc

        # Always reconcile payload indexes, including for a pre-existing
        # collection. Done after the create step so a failure is not masked by
        # the self._ensured short-circuit above.
        self._ensure_payload_indexes(client)
        self._ensured = True

    def drop_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError("Could not drop the collection.") from exc
        self._ensured = False

    # ---------------- writes ----------------

    def upsert(self, points: list[dict[str, Any]]) -> int:
        """Insert/replace points: ``[{id, vector, text, metadata}, ...]``."""
        if not points:
            return 0
        client = self.client
        structs = []
        for point in points:
            vector = point["vector"]
            metadata = dict(point.get("metadata") or {})
            metadata["text"] = point["text"]
            structs.append(
                qmodels.PointStruct(
                    id=point.get("id") or uuid.uuid4().hex,
                    vector=[float(x) for x in vector],
                    payload=metadata,
                )
            )
        try:
            client.upsert(collection_name=self.collection_name, points=structs, wait=True)
        except Exception as exc:  # noqa: BLE001
            log.error(safe_provider_error(exc, "qdrant.upsert"))
            raise VectorStoreError("Could not store the document vectors.") from exc
        return len(structs)

    def delete_by_source(self, source: str) -> None:
        """Remove every chunk belonging to one source file (re-ingest safety)."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="source", match=qmodels.MatchValue(value=source)
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(safe_provider_error(exc, "qdrant.delete_by_source"))
            raise VectorStoreError("Could not remove the previous vectors.") from exc

    def count(self) -> int:
        try:
            return int(
                self.client.count(collection_name=self.collection_name, exact=True).count
            )
        except Exception as exc:  # noqa: BLE001
            log.error(safe_provider_error(exc, "qdrant.count"))
            raise VectorStoreError("Could not read the vector store.") from exc

    # ---------------- reads ----------------

    def search(self, vector: list[float], top_k: int, min_score: float | None = None) -> list[dict]:
        """Similarity search. Returns ``[{text, score, metadata}, ...]``."""
        client = self.client
        try:
            response = client.query_points(
                collection_name=self.collection_name,
                query=[float(x) for x in vector],
                limit=int(top_k),
                score_threshold=min_score,
                with_payload=True,
            )
            hits = response.points
        except Exception as exc:  # noqa: BLE001
            log.error(safe_provider_error(exc, "qdrant.query_points"))
            raise VectorStoreError("Could not search the vector store.") from exc

        results: list[dict] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            text = payload.pop("text", "") or ""
            results.append(
                {
                    "id": hit.id,
                    "text": text,
                    "score": float(hit.score) if hit.score is not None else None,
                    "metadata": payload,
                }
            )
        return results


@lru_cache(maxsize=1)
def get_vector_store() -> QdrantVectorStore:
    return QdrantVectorStore()


def reset_vector_store_cache() -> None:
    get_vector_store.cache_clear()