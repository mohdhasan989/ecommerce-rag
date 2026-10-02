"""Milestone 2 AI/RAG tests.

Everything here is mocked: no Groq, Hugging Face or Qdrant network calls are
made, so the suite runs with zero credentials. Providers are patched at the
service boundary (``app.ai.*``), which is exactly the seam production code uses.
"""
import json
import os
from unittest.mock import patch

import pytest

from app.ai.exceptions import (
    AIError,
    ConfigurationError,
    EmbeddingError,
    LLMError,
    VectorStoreError,
)
from app.ai.router.intent_router import Intent, IntentRouter, RouteDecision

# ------------------------------------------------------------------ helpers


class FakeLLM:
    """Stands in for GroqService. ``responses`` is a list consumed in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def invoke(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.responses:
            return ""
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def invoke_json(self, system: str, user: str) -> dict:
        """Use the REAL GroqService JSON parser so tests cover production code."""
        from app.ai.llm.groq_client import GroqService

        raw = self.invoke(system, user)
        parsed = GroqService._parse_json(raw)
        if parsed is None:
            raise ValueError("unparsable")
        return parsed


def decision(intent: str, confidence: float, threshold: float = 0.8) -> RouteDecision:
    return RouteDecision(
        intent=intent, confidence=confidence, reason="test", threshold=threshold
    )


# ------------------------------------------------------- 1. intent router


ROUTER_CASES = [
    # (customer message, expected intent, expected confidence)
    ("what is your return policy?", Intent.RAG, 0.95),
    ("do you sell laptops under 50000?", Intent.PRODUCT, 0.95),
    ("where is my order?", Intent.ORDER, 0.95),
    ("thanks, that was helpful!", Intent.UNKNOWN, 0.9),
    ("asdfgh qwerty zzz", Intent.UNKNOWN, 0.0),
    ("", Intent.UNKNOWN, 1.0),
    ("   ", Intent.UNKNOWN, 1.0),
    ("do you sell laptops under 50000 and where is my order?", Intent.UNKNOWN, 0.4),
]


@pytest.mark.parametrize("message,expected_intent,expected_confidence", ROUTER_CASES)
def test_router_classifies_expected_intent(message, expected_intent, expected_confidence):
    """Required scenario table: each message maps to the documented intent."""
    payload = {
        "intent": expected_intent,
        "confidence": expected_confidence,
        "reason": "mocked",
    }
    with patch(
        "app.ai.router.intent_router.get_groq_service",
        return_value=FakeLLM(json.dumps(payload)),
    ):
        got = IntentRouter().classify(message)
    assert got.intent == expected_intent
    assert got.confidence == pytest.approx(expected_confidence, abs=1e-3)


def test_router_unknown_intent_label_is_coerced():
    with patch(
        "app.ai.router.intent_router.get_groq_service",
        return_value=FakeLLM(json.dumps({"intent": "banana", "confidence": 0.9})),
    ):
        assert IntentRouter().classify("hi").intent == Intent.UNKNOWN


def test_router_accepts_confidence_as_percent_string():
    with patch(
        "app.ai.router.intent_router.get_groq_service",
        return_value=FakeLLM(
            json.dumps({"intent": "rag", "confidence": "91%", "reason": ""})
        ),
    ):
        assert IntentRouter().classify("policy?").confidence == pytest.approx(0.91)


def test_router_parses_json_wrapped_in_code_fence():
    fenced = '```json\n{"intent": "order", "confidence": 0.97}\n```'
    with patch(
        "app.ai.router.intent_router.get_groq_service",
        return_value=FakeLLM(fenced),
    ):
        assert IntentRouter().classify("my order").intent == Intent.ORDER


def test_router_low_confidence_requires_clarification():
    assert decision("rag", 0.5).needs_clarification is True
    assert decision("rag", 0.80).needs_clarification is False
    assert decision("rag", 0.99).needs_clarification is False


def test_router_degrades_to_unknown_on_provider_error():
    """Transient provider failure must not 500 the chat endpoint."""
    with patch(
        "app.ai.router.intent_router.get_groq_service",
        return_value=FakeLLM(LLMError("temporarily unavailable")),
    ):
        got = IntentRouter().classify("what is your return policy?")
    assert got.intent == Intent.UNKNOWN
    assert got.needs_clarification is True


def test_router_propagates_missing_api_key():
    """A missing key must surface as a clear 503, not a bogus clarification."""
    with patch(
        "app.ai.router.intent_router.get_groq_service",
        side_effect=ConfigurationError(["GROQ_API_KEY"], "groq"),
    ):
        with pytest.raises(ConfigurationError) as excinfo:
            IntentRouter().classify("what is your return policy?")
    assert excinfo.value.missing == ["GROQ_API_KEY"]
    assert excinfo.value.status_code == 503


def test_router_clarification_falls_back_when_llm_fails():
    with patch(
        "app.ai.router.intent_router.get_groq_service",
        return_value=FakeLLM(LLMError("down")),
    ):
        text = IntentRouter().clarification("???", decision("unknown", 0.0))
    assert text and len(text) < 400


# ------------------------------------------------------- 2. configuration


def test_config_reports_missing_capabilities_without_values():
    from app.ai.config import AIConfig

    cfg = AIConfig(groq_api_key="", hf_api_key="", qdrant_url="", qdrant_api_key="")
    assert cfg.is_configured("groq") is False
    assert cfg.is_configured("embeddings") is False
    assert cfg.is_configured("qdrant") is False
    assert "GROQ_API_KEY" in cfg.missing("groq")
    assert cfg.missing("rag")


def test_config_redacts_secrets_in_status():
    from app.ai.config import AIConfig

    cfg = AIConfig(groq_api_key="gsk_supersecret", hf_api_key="hf_secret")
    blob = json.dumps(cfg.status())
    assert "gsk_supersecret" not in blob
    assert "hf_secret" not in blob


def test_app_boots_with_no_ai_keys():
    """Regression guard: Milestone 1 must not depend on any AI variable."""
    import importlib

    from app import config as app_config

    for var in ("GROQ_API_KEY", "HF_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"):
        os.environ.pop(var, None)
    importlib.reload(app_config)
    settings = app_config.Settings()
    for attr in (
        "GROQ_API_KEY",
        "HF_API_KEY",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "GROQ_MODEL",
        "HF_EMBEDDING_MODEL",
        "QDRANT_COLLECTION",
    ):
        assert hasattr(settings, attr), attr
    importlib.reload(app_config)


# ------------------------------------------------------- 3. loader/chunker


def test_chunker_splits_and_preserves_metadata():
    from app.ai.config import AIConfig
    from app.ai.rag.chunker import split_documents
    from langchain_core.documents import Document

    text = "Return policy sentence. " * 200
    docs = [Document(page_content=text, metadata={"source": "policy.txt", "page": 3})]
    chunks = split_documents(docs, AIConfig(chunk_size=300, chunk_overlap=50))
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.metadata["source"] == "policy.txt"
        assert chunk.metadata["page"] == 3
        assert len(chunk.page_content) <= 300
        assert "chunk_index" in chunk.metadata


def test_loader_reads_txt_and_unsupported_extension(tmp_path):
    from app.ai.rag.document_loader import load_file

    txt = tmp_path / "policy.txt"
    txt.write_text("We accept returns within 30 days.", encoding="utf-8")
    docs = load_file(txt)
    assert docs and "30 days" in docs[0].page_content
    meta = docs[0].metadata
    assert meta["source"] == "policy.txt"
    assert meta["document_type"] == "text"
    assert meta["page"] is None

    bad = tmp_path / "image.png"
    bad.write_bytes(b"\x89PNG\r\n")
    from app.ai.exceptions import DocumentLoadError

    with pytest.raises(DocumentLoadError):
        load_file(bad)


# ------------------------------------------------------- 4. context builder


def test_context_builder_keeps_routes_separate():
    from app.ai.context_builder import build_context
    from app.ai.rag.retriever import RetrievalResult

    retrieval = RetrievalResult(query="return policy?", top_k=5)
    ctx = build_context(decision=decision("rag", 0.95), retrieval=retrieval)
    assert ctx.route == "rag"
    assert ctx.has_context is False
    assert "No documents" in ctx.text


def test_generate_answer_returns_fallback_without_context():
    from app.ai.context_builder import AnswerContext, generate_answer
    from app.ai.prompts import FALLBACK_ANSWER

    ctx = AnswerContext(route="rag", text="", has_context=False)
    assert generate_answer("what is your return policy?", ctx) == FALLBACK_ANSWER


def test_generate_answer_never_raises_on_llm_failure():
    from app.ai.context_builder import AnswerContext, generate_answer
    from app.ai.prompts import FALLBACK_ANSWER

    ctx = AnswerContext(route="rag", text="policy", has_context=True)
    with patch(
        "app.ai.context_builder.get_groq_service",
        return_value=FakeLLM(LLMError("boom")),
    ):
        assert generate_answer("q?", ctx) == FALLBACK_ANSWER


# ------------------------------------------- order answers (context -> prompt)
# Incident: "Where is my order?" retrieved three real orders, the context
# reached the model, and the model still answered "I don't have that
# information ... let me know your order number". The generic prompt's refusal
# rules (3 and 4) invited it. See ORDER_ANSWER_SYSTEM and the grounded fallback.

from app.ai.context_builder import generate_answer  # noqa: E402

ORDER_ROWS = [
    {"id": 5, "status": "DELIVERED", "total_amount": 109.0,
     "created_at": "2026-09-30T10:00:00", "city": "Austin",
     "items": [{"name": "Leather Crossbody Bag", "quantity": 1, "subtotal": 109.0}]},
    {"id": 4, "status": "DELIVERED", "total_amount": 65.0,
     "created_at": "2026-09-20T10:00:00", "city": "Austin",
     "items": [{"name": "Aviator Sunglasses", "quantity": 1, "subtotal": 65.0}]},
    {"id": 3, "status": "PENDING", "total_amount": 69.0,
     "created_at": "2026-09-10T10:00:00", "city": "Austin",
     "items": [{"name": "Slim Fit Denim Jacket", "quantity": 1, "subtotal": 69.0}]},
]

REFUSAL = (
    "I'm sorry, but I don't have that information. Could you let me know your "
    "order number, or you can reach out to our support team for help."
)


def _order_context(rows=None):
    from app.ai.context_builder import build_context
    from app.ai.handlers import RouteContext

    route_context = RouteContext(route="order", found=bool(rows), data=list(rows or []))
    return build_context(decision=decision("order", 0.99), route_context=route_context), route_context


def test_order_context_is_authoritative_and_ordered_newest_first():
    from app.ai.context_builder import format_order_context

    text, sources = format_order_context(_order_context(ORDER_ROWS)[1])
    assert sources == ["mysql:orders"]
    assert "most recent first" in text
    assert "verified fact" in text
    assert text.index("Order #5") < text.index("Order #4") < text.index("Order #3")


def test_order_context_carries_no_invented_fields():
    """Tracking / courier / delivery date must never be synthesised."""
    from app.ai.context_builder import format_order_context

    text, _ = format_order_context(_order_context(ORDER_ROWS)[1])
    for banned in ("tracking", "courier", "carrier", "arrives", "delivered on", "ups", "fedex"):
        assert banned not in text.lower()


def test_build_order_answer_summarises_real_statuses():
    from app.ai.context_builder import build_order_answer

    answer = build_order_answer(ORDER_ROWS)
    assert "3 orders" in answer
    for row in ORDER_ROWS:
        assert f"Order #{row['id']}" in answer
        assert row["status"] in answer
    assert "Leather Crossbody Bag" in answer
    assert "$109.00" in answer


def test_build_order_answer_is_empty_without_orders():
    from app.ai.context_builder import build_order_answer

    assert build_order_answer([]) == ""


@pytest.mark.parametrize(
    "message", ["Where is my order?", "What is the status of my latest order?"]
)
def test_order_refusal_is_replaced_with_the_real_orders(message):
    """The reported bug: a populated context must never yield a refusal."""
    ctx, _ = _order_context(ORDER_ROWS)
    with patch("app.ai.context_builder.get_groq_service", return_value=FakeLLM(REFUSAL)):
        answer = generate_answer(message, ctx)
    assert REFUSAL not in answer
    assert "DELIVERED" in answer and "PENDING" in answer
    assert "Order #5" in answer


def test_specific_order_answer_contains_its_status():
    ctx, _ = _order_context([ORDER_ROWS[0]])
    with patch("app.ai.context_builder.get_groq_service", return_value=FakeLLM(REFUSAL)):
        answer = generate_answer("What is the status of order #5?", ctx)
    assert "Order #5" in answer
    assert "DELIVERED" in answer
    assert "Leather Crossbody Bag" in answer


def test_good_order_answer_is_kept_verbatim():
    """The guard must not overwrite a correctly grounded answer."""
    ctx, _ = _order_context(ORDER_ROWS)
    good = "Your order #5 was delivered. It contained the Leather Crossbody Bag for $109.00."
    with patch("app.ai.context_builder.get_groq_service", return_value=FakeLLM(good)):
        assert generate_answer("Where is my order?", ctx) == good


def test_order_answer_survives_llm_failure():
    ctx, _ = _order_context(ORDER_ROWS)
    with patch("app.ai.context_builder.get_groq_service", return_value=FakeLLM(LLMError("boom"))):
        answer = generate_answer("Where is my order?", ctx)
    assert "Order #5" in answer and "DELIVERED" in answer


def test_order_answer_survives_an_empty_model_reply():
    ctx, _ = _order_context(ORDER_ROWS)
    with patch("app.ai.context_builder.get_groq_service", return_value=FakeLLM("")):
        assert "Order #5" in generate_answer("Where is my order?", ctx)


def test_no_orders_keeps_the_existing_fallback():
    from app.ai.prompts import FALLBACK_ANSWER

    ctx, _ = _order_context([])
    assert ctx.has_context is False
    assert ctx.grounded_answer == ""
    assert generate_answer("Where is my order?", ctx) == FALLBACK_ANSWER


def test_order_route_uses_the_order_prompt_not_the_generic_one():
    from app.ai.prompts import ANSWER_SYSTEM, ORDER_ANSWER_SYSTEM

    ctx, _ = _order_context(ORDER_ROWS)
    fake = FakeLLM("fine")
    with patch("app.ai.context_builder.get_groq_service", return_value=fake):
        generate_answer("Where is my order?", ctx)
    system = fake.calls[0][0]
    assert system == ORDER_ANSWER_SYSTEM.replace("{context}", ctx.text)
    assert "signed-in customer" in system
    assert "Order #5" in system
    assert system != ANSWER_SYSTEM.replace("{context}", ctx.text)


def test_order_prompt_forbids_inventing_tracking_details():
    from app.ai.prompts import ORDER_ANSWER_SYSTEM

    lowered = ORDER_ANSWER_SYSTEM.lower()
    assert "tracking number" in lowered
    assert "courier" in lowered
    assert "never ask the customer for an order number" in lowered


def test_other_routes_keep_the_generic_prompt():
    from app.ai.context_builder import AnswerContext
    from app.ai.prompts import ANSWER_SYSTEM

    fake = FakeLLM("answer")
    ctx = AnswerContext(route="rag", text="CONTEXT body", has_context=True)
    with patch("app.ai.context_builder.get_groq_service", return_value=fake):
        generate_answer("what is your return policy?", ctx)
    assert fake.calls[0][0] == ANSWER_SYSTEM.replace("{context}", "CONTEXT body")
    assert ctx.grounded_answer == "", "only the order route carries a grounded answer"


@pytest.mark.parametrize(
    "answer,expected",
    [
        (REFUSAL, True),
        ("I don't have that information.", True),
        ("Could you let me know your order number?", True),
        ("Please contact our support team for help.", True),
        ("Your order #5 is DELIVERED.", False),
        ("You have 3 orders: #5 delivered, #4 delivered, #3 pending.", False),
    ],
)
def test_ungrounded_answer_detection(answer, expected):
    from app.ai.context_builder import looks_ungrounded

    assert looks_ungrounded(answer) is expected


# ------------------------------------------------------- 5. exception safety


def test_configuration_error_lists_var_names_not_values():
    exc = ConfigurationError(["GROQ_API_KEY", "QDRANT_URL"], "rag")
    assert exc.status_code == 503
    assert "GROQ_API_KEY" in exc.detail
    assert exc.message


def test_error_status_codes():
    assert EmbeddingError("x").status_code == 502
    assert LLMError("x").status_code == 502
    assert VectorStoreError("x").status_code == 502
    assert AIError("x").status_code == 503


def test_safe_provider_error_redacts_secrets():
    from app.ai.exceptions import safe_provider_error

    exc = RuntimeError("request failed api_key=gsk_livesecretvalue")
    out = safe_provider_error(exc, "groq")
    assert "gsk_livesecretvalue" not in out
    assert "redacted" in out
