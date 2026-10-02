"""Ingestion and vector-store tests.

The embedding provider and the Qdrant client are both mocked, so these verify
our own logic - payload shaping, deterministic IDs, threshold filtering and the
no-results path - without any network access.
"""
import uuid
from unittest.mock import patch

import pytest
from langchain_core.documents import Document
from qdrant_client.http import models as qmodels

from app.ai.config import AIConfig
from app.ai.exceptions import EmbeddingError, VectorStoreError
from app.ai.rag.retriever import RetrievedChunk, RetrievalResult


class StubEmbeddings:
    """Deterministic fake vectors of a configurable width."""

    def __init__(self, dim=384):
        self.dim = dim
        self.calls = []

    def embed_documents(self, texts):
        self.calls.append(list(texts))
        return [[0.1] * self.dim for _ in texts]

    def embed_query(self, text):
        self.calls.append([text])
        return [0.1] * self.dim

    def dimension(self):
        return self.dim


class _FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self.reason_phrase = "Test"
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")  # what httpx does on an HTML error page
        return self._payload


class _FakeHTTPClient:
    """Stands in for httpx.Client inside HFEmbeddings."""

    def __init__(self, response=None, error=None):
        self.response, self.error = response, error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def _embeddings(response=None, error=None):
    from app.ai.embeddings.hf_embeddings import HFEmbeddings

    return HFEmbeddings(
        AIConfig(hf_api_key="hf_test", hf_api_url="https://api.test"),
        client=_FakeHTTPClient(response=response, error=error),
    )


# --------------------------------------------------------------- ingestion


def test_build_points_shape_and_ids_are_deterministic():
    from app.ai.rag.ingestion import build_points

    chunks = [
        Document(page_content="a", metadata={"source": "p.md", "page": None, "chunk_index": 0}),
        Document(page_content="b", metadata={"source": "p.md", "page": 2, "chunk_index": 1}),
    ]
    with patch("app.ai.rag.ingestion.get_embeddings", return_value=StubEmbeddings(384)):
        first = build_points(chunks)
        second = build_points(chunks)

    assert len(first) == 2
    for point in first:
        assert set(point) == {"id", "vector", "text", "metadata"}
        assert len(point["vector"]) == 384
        assert point["text"] in ("a", "b")

    # Re-ingesting identical content must not create duplicate vectors.
    assert [p["id"] for p in first] == [p["id"] for p in second]


def test_build_points_drops_none_metadata():
    """Qdrant rejects null payload values, so None must be stripped."""
    from app.ai.rag.ingestion import build_points

    chunk = Document(
        page_content="a",
        metadata={"source": "p.md", "page": None, "chunk_index": 0, "document_type": "md"},
    )
    with patch("app.ai.rag.ingestion.get_embeddings", return_value=StubEmbeddings()):
        point = build_points([chunk])[0]
    assert "page" not in point["metadata"]
    assert point["metadata"]["source"] == "p.md"
    assert point["metadata"]["document_type"] == "md"


def test_point_ids_are_valid_uuid5():
    from app.ai.rag.ingestion import build_points

    chunk = Document(page_content="a", metadata={"source": "p.md", "chunk_index": 3})
    with patch("app.ai.rag.ingestion.get_embeddings", return_value=StubEmbeddings()):
        point_id = build_points([chunk])[0]["id"]
    parsed = uuid.UUID(point_id)
    assert parsed.version == 5


def test_build_points_empty_input_needs_no_provider():
    from app.ai.rag.ingestion import build_points

    assert build_points([]) == []


def test_ingest_fails_loudly_without_configuration(monkeypatch):
    """With no keys set, ingestion must raise rather than silently no-op.

    Hermetic: ``get_embeddings``/``get_vector_store`` are lru_cached singletons
    that read real ``.env`` values, so this injects an unconfigured store
    instead of relying on the developer's own ``.env`` being blank.
    """
    from app.ai.exceptions import AIError
    from app.ai.rag import ingestion
    from app.ai.vectorstore.qdrant_client import QdrantVectorStore

    empty = AIConfig()
    assert empty.missing("qdrant"), "fixture sanity: this config is unconfigured"

    monkeypatch.setattr(ingestion, "get_embeddings", lambda: StubEmbeddings())
    monkeypatch.setattr(
        ingestion, "get_vector_store", lambda: QdrantVectorStore(empty)
    )

    with pytest.raises(AIError):
        ingestion.ingest_documents(
            [Document(page_content="x", metadata={"source": "a.txt"})],
            config=empty,
        )


# --------------------------------------------------------------- retrieval


def test_retrieve_normalises_hits_into_chunks():
    from app.ai.rag.retriever import retrieve

    config = AIConfig(groq_api_key="k", hf_api_key="k",
                      qdrant_url="https://x", qdrant_api_key="k", min_score=0.30)

    class FakeStore:
        def __init__(self):
            self.searched = None

        def search(self, vector, top_k, min_score):
            self.searched = (top_k, min_score)
            # Qdrant returns whole payload rows; empty text must be dropped.
            return [
                {"id": "u1", "text": "Returns within 30 days.", "score": 0.91,
                 "metadata": {"source": "a.md", "page": 1}},
                {"id": "u2", "text": "   ", "score": 0.88,
                 "metadata": {"source": "b.md"}},
            ]

    store = FakeStore()
    with patch("app.ai.rag.retriever.get_embeddings", return_value=StubEmbeddings()), patch(
        "app.ai.rag.retriever.get_vector_store", return_value=store
    ):
        result = retrieve("return policy?", top_k=5, config=config)

    assert store.searched == (5, 0.30), "min_score must reach Qdrant"
    assert len(result.chunks) == 1, "blank chunks must be discarded"
    assert result.chunks[0].text == "Returns within 30 days."
    assert result.chunks[0].score == 0.91
    assert result.chunks[0].metadata["source"] == "a.md"
    assert result.is_empty is False


def test_retrieve_returns_empty_when_question_blank():
    from app.ai.rag.retriever import retrieve

    result = retrieve("   ", config=AIConfig(hf_api_key="k", qdrant_url="https://x",
                                             qdrant_api_key="k"))
    assert result.is_empty is True
    assert result.chunks == []


def test_retrieval_result_empty_when_nothing_found():
    from app.ai.rag.retriever import RetrievalResult

    result = RetrievalResult(query="q", top_k=5)
    assert result.is_empty is True
    assert result.as_dict()["count"] == 0


def test_embedding_provider_failure_becomes_embedding_error():
    emb = _embeddings(error=OSError("connection reset"))
    with pytest.raises(EmbeddingError):
        emb.embed_query("hello")


def test_embeddings_validate_vector_shape():
    emb = _embeddings(response=_FakeResponse(200, [[1.0, 2.0, 3.0]]))
    assert emb.embed_query("hello") == [1.0, 2.0, 3.0]


def test_embeddings_http_error_is_wrapped():
    emb = _embeddings(response=_FakeResponse(401, None, text="unauthorized"))
    with pytest.raises(EmbeddingError) as excinfo:
        emb.embed_query("hello")
    assert "hf_test" not in str(excinfo.value), "the key must never leak into an error"


def test_embeddings_send_the_api_key_and_model():
    emb = _embeddings(response=_FakeResponse(200, [[0.5, 0.5]]))
    emb.embed_query("hello")
    url, kwargs = emb._client.calls[0]
    assert "bge-small-en-v1.5" in url
    assert kwargs.get("headers", {}).get("Authorization") == "Bearer hf_test"


# --------------------------------------------- endpoint (regression guards)
# Incident: HF retired api-inference.huggingface.co, so the endpoint stopped
# resolving and runtime dimension discovery failed with
# "Could not determine the vector dimension for this embedding model."
LEGACY_HOST = "https://api-inference.huggingface.co"
ROUTER_BASE = "https://router.huggingface.co/hf-inference"


def _endpoint_for(base: str) -> str:
    from app.ai.embeddings.hf_embeddings import HFEmbeddings

    return HFEmbeddings(AIConfig(hf_api_key="hf_test", hf_api_url=base))._endpoint


def test_default_endpoint_uses_the_hf_router():
    from app.config import Settings

    # Assert the declared default, not settings.HF_API_URL: the latter is
    # whatever the developer's own .env happens to contain.
    declared = Settings.model_fields["HF_API_URL"].default
    assert "api-inference" not in declared
    assert declared == ROUTER_BASE
    assert _endpoint_for(ROUTER_BASE) == f"{ROUTER_BASE}/models/BAAI/bge-small-en-v1.5"


def test_ai_config_default_also_points_at_the_router():
    from app.ai.config import AIConfig

    assert AIConfig().hf_api_url == ROUTER_BASE


def test_retired_legacy_host_is_mapped_to_the_router():
    """An existing .env pointing at the dead host must still work."""
    assert _endpoint_for(LEGACY_HOST) == f"{ROUTER_BASE}/models/BAAI/bge-small-en-v1.5"
    assert _endpoint_for(LEGACY_HOST + "/") == f"{ROUTER_BASE}/models/BAAI/bge-small-en-v1.5"


def test_feature_extraction_provider_is_not_used():
    """That provider rejects this model: 'Model not supported by provider
    hf-inference'. Guard against the old /pipeline/... path coming back."""
    for base in (LEGACY_HOST, ROUTER_BASE):
        assert "pipeline" not in _endpoint_for(base)


# --------------------------------------------- error detail (no leaks)


@pytest.mark.parametrize(
    "status,payload,expected",
    [
        (400, {"error": "Model not supported by provider hf-inference"},
         "Model not supported by provider hf-inference"),
        (401, {"error": "Invalid credentials in Authorization header"}, "Invalid credentials"),
        (404, {"error": "Model not found"}, "Model not found"),
        (429, {"error": "Rate limit reached"}, "Rate limit reached"),
    ],
)
def test_provider_error_detail_is_surfaced(status, payload, expected):
    """Provider-specific reasons must be diagnosable, not flattened away."""
    from app.ai.embeddings.hf_embeddings import HFEmbeddings

    emb = HFEmbeddings(AIConfig(hf_api_key="hf_test", hf_api_url="https://api.test"))
    message = emb._explain(_FakeResponse(status, payload))
    assert expected in message


def test_error_messages_never_leak_the_api_key():
    from app.ai.embeddings.hf_embeddings import HFEmbeddings

    secret = "hf_LEAKCANARY0000000000000000000"
    emb = HFEmbeddings(AIConfig(hf_api_key=secret, hf_api_url="https://api.test"))
    message = emb._explain(_FakeResponse(400, {"error": f"token {secret} rejected"}))
    assert secret not in message
    assert "hf_REDACTED" in message


def test_error_messages_survive_non_json_body():
    from app.ai.embeddings.hf_embeddings import HFEmbeddings

    emb = HFEmbeddings(AIConfig(hf_api_key="hf_test", hf_api_url="https://api.test"))
    assert emb._explain(_FakeResponse(502, None, text="<html>bad gateway</html>"))


# --------------------------------------------- dimension discovery


def test_dimension_uses_the_probe_not_metadata():
    """The probe is authoritative; metadata must not be consulted."""
    emb = _embeddings(response=_FakeResponse(200, [[0.1, 0.2, 0.3, 0.4]]))
    with patch.object(emb, "_hidden_size_from_metadata") as meta:
        assert emb.dimension() == 4
    assert meta.called is False, "a successful probe must not need metadata"


def test_dimension_falls_back_to_repo_config_json():
    """The /api/models payload omits hidden_size for BERT encoders, so the
    repo's config.json must be consulted."""
    emb = _embeddings()
    with patch("app.ai.embeddings.hf_embeddings.httpx.get") as get:
        get.return_value = _FakeResponse(200, {"hidden_size": 384})
        assert emb._hidden_size_from_metadata() == 384
    assert "config.json" in get.call_args[0][0]


def test_dimension_fallback_returns_none_when_unknown():
    emb = _embeddings()
    with patch("app.ai.embeddings.hf_embeddings.httpx.get") as get:
        get.return_value = _FakeResponse(200, {"config": {"model_type": "bert"}})
        assert emb._hidden_size_from_metadata() is None


def test_dimension_error_names_the_problem_when_probe_and_metadata_fail():
    from app.ai.embeddings.hf_embeddings import HFEmbeddings

    emb = HFEmbeddings(AIConfig(hf_api_key="hf_test", hf_api_url="https://api.test"))
    with patch.object(emb, "_embed", side_effect=EmbeddingError("boom")), patch.object(
        emb, "_hidden_size_from_metadata", return_value=None
    ):
        with pytest.raises(EmbeddingError) as excinfo:
            emb.dimension()
    assert "dimension" in str(excinfo.value).lower()


# --------------------------------------------------------------- qdrant


def test_qdrant_operations_use_modern_query_points():
    from app.ai.vectorstore.qdrant_client import QdrantVectorStore

    class FakeClient:
        def __init__(self):
            self.upserts, self.deletes = [], []

        def collection_exists(self, name):
            return True

        def query_points(self, **kwargs):
            self.last_query = kwargs

            class P:
                def __init__(self, sid, score, payload):
                    self.id, self.score, self.payload = sid, score, payload

            class R:
                points = [P("u1", 0.8, {"text": "hello", "source": "a.md"})]

            return R()

        def upsert(self, collection_name, points, **kw):
            self.upserts.append((collection_name, points))

        def delete(self, collection_name, points_selector, **kw):
            self.deletes.append((collection_name, points_selector))

        def count(self, collection_name, **kw):
            class R:
                count = 7

            return R()

    store = QdrantVectorStore(
        AIConfig(hf_api_key="k", qdrant_url="https://x", qdrant_api_key="k",
                 qdrant_collection="coll"),
        client=FakeClient(),
    )

    hits = store.search([0.1] * 4, top_k=3, min_score=0.2)
    assert hits and hits[0]["score"] == 0.8
    assert hits[0]["text"] == "hello"
    assert "text" not in hits[0]["metadata"], "text is lifted out of the payload"
    assert store.count() == 7


def test_qdrant_wraps_provider_errors():
    from app.ai.vectorstore.qdrant_client import QdrantVectorStore

    class Broken:
        def query_points(self, **kwargs):
            raise RuntimeError("qdrant exploded")

    store = QdrantVectorStore(
        AIConfig(hf_api_key="k", qdrant_url="https://x", qdrant_api_key="k"),
        client=Broken(),
    )
    with pytest.raises(VectorStoreError):
        store.search([0.1] * 4, top_k=3, min_score=0.2)


# ------------------------------------- qdrant payload indexes (source keyword)
# Qdrant rejects a filtered delete on an unindexed field with HTTP 400
# "Index required but not found for \"source\" ... [keyword]", which is what
# stopped ingestion after embeddings succeeded.


class _FakeIndexInfo:
    def __init__(self, data_type):
        self.data_type = data_type


class _FakeCollectionInfo:
    def __init__(self, payload_schema):
        self.payload_schema = payload_schema
        self.status = "green"
        self.points_count = 0


class _StatefulQdrant:
    """Mimics the Qdrant rules that matter here.

    * a filtered delete needs a keyword index on the filtered field
    * re-creating a collection is destructive and tracked
    * create_payload_index is recorded so we can assert idempotency
    """

    def __init__(self, exists=True, schema=None):
        self.exists = exists
        self.schema = dict(schema or {})
        self.created_collections = []
        self.created_indexes = []
        self.deletes = []

    def collection_exists(self, name):
        return self.exists

    def create_collection(self, collection_name, vectors_config, **kw):
        self.created_collections.append((collection_name, vectors_config))
        self.exists = True

    def get_collection(self, collection_name):
        return _FakeCollectionInfo(self.schema)

    def create_payload_index(self, collection_name, field_name, field_schema, **kw):
        self.created_indexes.append((field_name, field_schema))
        self.schema[field_name] = _FakeIndexInfo(field_schema)

    def delete(self, collection_name, points_selector, **kw):
        # Reproduce Qdrant's real precondition check.
        field = points_selector.filter.must[0].key
        if field not in self.schema:
            raise RuntimeError(
                f'Bad request: Index required but not found for "{field}" of one of '
                "the following types: [keyword]. Help: Create an index for this key "
                "or use a different filter."
            )
        self.deletes.append((collection_name, field))

    def upsert(self, collection_name, points, **kw):
        self.upserts = getattr(self, "upserts", [])
        self.upserts.append((collection_name, points))


def _store(client):
    from app.ai.vectorstore.qdrant_client import QdrantVectorStore

    return QdrantVectorStore(
        AIConfig(hf_api_key="k", qdrant_url="https://x", qdrant_api_key="k",
                 qdrant_collection="ecommerce_knowledge"),
        client=client,
    )


def test_new_collection_gets_source_keyword_index():
    """A freshly created collection must be immediately deletable by source."""
    from qdrant_client.http import models as qmodels

    client = _StatefulQdrant(exists=False)
    store = _store(client)
    store.ensure_collection(vector_size=384)

    assert client.created_collections, "collection should have been created"
    _, vectors = client.created_collections[0]
    assert vectors.size == 384
    assert vectors.distance == qmodels.Distance.COSINE
    assert ("source", qmodels.PayloadSchemaType.KEYWORD) in client.created_indexes


def test_existing_collection_without_source_index_gets_one():
    """The live incident: collection existed with zero payload indexes, and
    ensure_collection() returned early without ever creating them."""
    from qdrant_client.http import models as qmodels

    client = _StatefulQdrant(exists=True, schema={})
    store = _store(client)
    store.ensure_collection(vector_size=384)

    assert client.created_collections == [], "must not recreate an existing collection"
    assert ("source", qmodels.PayloadSchemaType.KEYWORD) in client.created_indexes
    assert client.schema["source"].data_type == qmodels.PayloadSchemaType.KEYWORD


def test_existing_source_index_is_not_recreated():
    """Idempotency: an already-correct index must be left alone."""
    from qdrant_client.http import models as qmodels

    client = _StatefulQdrant(
        exists=True, schema={"source": _FakeIndexInfo(qmodels.PayloadSchemaType.KEYWORD)}
    )
    store = _store(client)
    store.ensure_collection(vector_size=384)

    assert client.created_indexes == [], "index already present must not be recreated"
    assert client.created_collections == []


def test_source_index_is_repaired_when_wrong_type():
    from qdrant_client.http import models as qmodels

    client = _StatefulQdrant(
        exists=True, schema={"source": _FakeIndexInfo(qmodels.PayloadSchemaType.INTEGER)}
    )
    store = _store(client)
    store.ensure_collection(vector_size=384)

    assert ("source", qmodels.PayloadSchemaType.KEYWORD) in client.created_indexes


def test_ensure_collection_is_idempotent_across_calls():
    """The _ensured short-circuit must not skip index reconciliation on the
    first call, and repeat calls must do nothing."""
    client = _StatefulQdrant(exists=False)
    store = _store(client)
    store.ensure_collection(vector_size=384)
    assert len(client.created_indexes) == 1

    store.ensure_collection(vector_size=384)
    assert len(client.created_indexes) == 1, "second call must be a no-op"


def test_delete_by_source_succeeds_after_ensure_collection():
    """The end-to-end guarantee: the exact sequence ingestion performs."""
    client = _StatefulQdrant(exists=True, schema={})
    store = _store(client)

    with pytest.raises(VectorStoreError):
        store.delete_by_source("return-policy.md")  # fails before the fix

    store.ensure_collection(vector_size=384)
    store.delete_by_source("return-policy.md")  # succeeds after
    assert ("ecommerce_knowledge", "source") in client.deletes


def test_delete_by_source_filters_on_the_source_field():
    from app.ai.vectorstore.qdrant_client import QdrantVectorStore

    client = _StatefulQdrant(
        exists=True, schema={"source": _FakeIndexInfo(qmodels.PayloadSchemaType.KEYWORD)}
    )
    store = QdrantVectorStore(
        AIConfig(hf_api_key="k", qdrant_url="https://x", qdrant_api_key="k"),
        client=client,
    )
    store.delete_by_source("shipping.md")
    _, field = client.deletes[0]
    assert field == "source"


def test_ensure_collection_wraps_index_creation_errors():
    class Failing(_StatefulQdrant):
        def create_payload_index(self, **kw):
            raise RuntimeError("index creation refused")

    store = _store(Failing(exists=True, schema={}))
    with pytest.raises(VectorStoreError):
        store.ensure_collection(vector_size=384)


def test_index_creation_failure_does_not_mark_store_as_ensured():
    """A failed reconcile must be retried next time, not silently skipped."""
    from qdrant_client.http import models as qmodels

    class Failing(_StatefulQdrant):
        fail = True

        def create_payload_index(self, collection_name, field_name, field_schema, **kw):
            if Failing.fail:
                raise RuntimeError("index creation refused")
            super().create_payload_index(
                collection_name, field_name, field_schema, **kw
            )

    client = Failing(exists=True, schema={})
    store = _store(client)

    with pytest.raises(VectorStoreError):
        store.ensure_collection(vector_size=384)
    assert store._ensured is False, "a failed ensure must not be cached as done"

    Failing.fail = False
    store.ensure_collection(vector_size=384)
    assert client.created_indexes == [("source", qmodels.PayloadSchemaType.KEYWORD)]
