"""Chat endpoint tests (Milestone 2).

Groq, embeddings and Qdrant are mocked, so no credentials are needed. The
product and order handlers are NOT mocked: they run for real against the seeded
test database, which is what proves the SQL filter and, critically, that a user
can never see another user's orders.
"""
import json
import re
from unittest.mock import patch

import pytest

from app.ai.config import AIConfig
from app.ai.exceptions import ConfigurationError
from app.ai.rag.retriever import RetrievedChunk, RetrievalResult

ROUTER_NAMESPACE = "app.routers.chatbot"

CONFIGURED = AIConfig(groq_api_key="gsk_test", hf_api_key="hf_test",
                      qdrant_url="https://example.qdrant.io", qdrant_api_key="qd_test")


class StubRouter:
    """Returns a pre-baked decision instead of calling an LLM."""

    def __init__(self, intent, confidence=0.95, threshold=0.8):
        self._intent, self._confidence, self._threshold = intent, confidence, threshold
        self.clarified = []

    def classify(self, message):
        from app.ai.router.intent_router import RouteDecision

        return RouteDecision(
            intent=self._intent, confidence=self._confidence,
            reason="stubbed", threshold=self._threshold,
        )

    def clarification(self, message, decision):
        self.clarified.append(message)
        return "Could you clarify what you need help with?"


@pytest.fixture()
def ai():
    """Patch every external seam the chat route touches.

    ``generate_answer`` is stubbed so the suite never performs a real Groq call;
    its failure handling is covered separately in test_ai.py.
    """
    with patch(f"{ROUTER_NAMESPACE}.get_ai_config", return_value=CONFIGURED), patch(
        f"{ROUTER_NAMESPACE}.generate_answer", return_value="Grounded answer."
    ):
        yield


@pytest.fixture()
def extractor():
    """Control the filter-extraction LLM used by the product/order handlers.

    Patched inside ``app.ai.handlers`` because that module calls
    ``get_groq_service`` directly. Without this the handlers would attempt a
    real network call and silently fall back to regex.
    """
    with patch("app.ai.handlers.get_groq_service") as mock:
        mock.return_value.invoke_json.return_value = {
            "search": None, "category": None, "max_price": None,
            "in_stock_only": False, "order_id": None, "status": None,
        }
        yield mock


def chat(client, message, router, ai, headers=None, retrieval=None):
    with patch(f"{ROUTER_NAMESPACE}.get_router", return_value=router), patch(
        f"{ROUTER_NAMESPACE}.retrieve", return_value=retrieval
    ) as retrieve_mock:
        response = client.post("/api/chat", json={"message": message}, headers=headers or {})
    return response, retrieve_mock


# ----------------------------------------------------------- RAG route


def test_rag_question_uses_retrieved_context(ai, client):
    router = StubRouter("rag")
    retrieval = RetrievalResult(
        chunks=[RetrievedChunk(text="Returns accepted within 30 days.",
                               score=0.87, metadata={"source": "returns.md", "page": 2})],
        query="return policy?", top_k=5,
    )
    response, retrieve_mock = chat(client, "what is your return policy?", router, ai,
                                   retrieval=retrieval)
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "rag"
    assert body["route"] == "rag"
    assert body["sources"] == ["returns.md, page 2"]
    assert retrieve_mock.called is True


def test_rag_with_no_chunks_gives_safe_answer(ai, client):
    router = StubRouter("rag")
    response, _ = chat(client, "what is your return policy?", router, ai,
                       retrieval=RetrievalResult(query="q", top_k=5))
    assert response.status_code == 200
    assert "could not find" in response.json()["answer"].lower()


# ----------------------------------------------------------- product route


def test_product_question_returns_seeded_products(ai, extractor, client):
    router = StubRouter("product")
    extractor.return_value.invoke_json.return_value["search"] = "laptop"
    response, retrieve_mock = chat(client, "do you sell laptops under 50000?", router, ai)
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "product"
    assert retrieve_mock.called is False, "product questions must not hit Qdrant"
    # The real handler ran against the seeded DB, so a match proves the query works.
    assert isinstance(body["debug"]["records"], list)


def test_product_handler_applies_price_filter(ai, extractor, client):
    """An impossible budget must yield no rows - proves max_price reaches SQL."""
    router = StubRouter("product")
    extractor.return_value.invoke_json.return_value["max_price"] = 1
    response, _ = chat(client, "anything under one dollar?", router, ai)
    assert response.status_code == 200
    records = response.json()["debug"]["records"]
    assert records == []
    assert all(r["effective_price"] <= 1 for r in records)


def test_product_handler_applies_category_filter(ai, extractor, client):
    router = StubRouter("product")
    extractor.return_value.invoke_json.return_value["category"] = "Books"
    response, _ = chat(client, "show me books", router, ai)
    assert response.status_code == 200
    records = response.json()["debug"]["records"]
    assert all(r["category"] == "Books" for r in records)


# ------------------------------------------- product price filters (regression)
# Incident: "Show me products under $100" returned found=false, count=0 even
# though `WHERE price <= 100` returns 13 rows. max_price had been extracted
# correctly, but search fell back to the whole raw message, so the query also
# applied LIKE '%Show me products under $100%' and matched nothing.


PRICE_PHRASES = [
    ("Show me products under $100", 100),
    ("Show me items below $500", 500),
    ("Show me products less than 1000", 1000),
    ("items under 5000", 5000),
    ("products under Rs 2500", 2500),
    ("products below \u20b9500", 500),
    ("cheapest laptops under 30000", 30000),
    ("anything at most 20 dollars", 20),
    ("products up to 99", 99),
    # Grouped thousands, Indian grouping, decimals and "k".
    ("products under $1,250", 1250),
    ("products under $1,299.99", 1299.99),
    ("products under 1,25,000", 125000),
    ("products under \u20b9 1,250", 1250),
    ("products under 50k", 50000),
]


@pytest.mark.parametrize("message,expected", PRICE_PHRASES)
def test_price_phrases_extract_max_price(message, expected):
    """No LLM: the regex fallback must carry the whole answer."""
    from app.ai.handlers import _parse_product_query

    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        query = _parse_product_query(message)
    assert query.max_price == float(expected)

    # The price phrase itself must not survive into the keyword search, which
    # is what silently produced zero rows.
    lowered = query.search.lower()
    assert "under" not in lowered and "below" not in lowered
    assert "at most" not in lowered and "up to" not in lowered
    assert "$" not in query.search and "rs" not in lowered
    assert str(int(expected)) not in query.search


def test_price_phrase_survives_an_extractor_that_omits_the_price():
    """A model returning nulls must not drop a ceiling stated in the message."""
    from app.ai.handlers import _parse_product_query

    with patch("app.ai.handlers.get_groq_service") as mock:
        mock.return_value.invoke_json.return_value = {
            "search": None, "category": None, "max_price": None,
        }
        query = _parse_product_query("Show me products under $100")
    assert query.max_price == 100.0
    assert query.search == ""


def test_explicitly_empty_search_is_trusted():
    """The model saying 'no keywords' must not be overridden by the raw message."""
    from app.ai.handlers import _parse_product_query

    with patch("app.ai.handlers.get_groq_service") as mock:
        mock.return_value.invoke_json.return_value = {
            "search": None, "category": None, "max_price": 100,
        }
        query = _parse_product_query("Show me products under $100")
    assert query.search == ""


def test_exact_name_search_is_preserved():
    from app.ai.handlers import _parse_product_query

    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        query = _parse_product_query("Show me Mechanical Keyboard")
    assert query.search == "Mechanical Keyboard"
    assert query.max_price is None


def test_model_keywords_still_win_when_present():
    from app.ai.handlers import _parse_product_query

    with patch("app.ai.handlers.get_groq_service") as mock:
        mock.return_value.invoke_json.return_value = {
            "search": "laptop", "category": None, "max_price": None,
        }
        query = _parse_product_query("do you sell laptops under 50000?")
    assert query.search == "laptop"
    assert query.max_price == 50000.0


def test_bare_numbers_are_not_a_budget():
    """'iPhone 15' is a model number, not a $15 ceiling."""
    from app.ai.handlers import _parse_product_query

    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        query = _parse_product_query("Show me iPhone 15")
    assert query.max_price is None
    assert query.search == "iPhone 15"


def test_keyword_search_combines_with_a_price_ceiling():
    from app.ai.handlers import _parse_product_query

    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        query = _parse_product_query("mechanical keyboards under $100")
    assert query.search == "mechanical keyboards"
    assert query.max_price == 100.0


def test_price_filter_returns_products_end_to_end(ai, extractor, client):
    """Full route against the seeded DB: real SQL, real filters."""
    router = StubRouter("product")
    response, _ = chat(client, "Show me products under $100", router, ai)
    assert response.status_code == 200
    body = response.json()

    route = body["debug"]["route_result"]
    records = body["debug"]["records"]
    assert route["route"] == "product"
    assert route["found"] is True, route
    assert records, "the $100 ceiling must match seeded products"
    assert route["count"] == len(records)

    assert route["filters"]["max_price"] == 100
    assert route["filters"]["search"] is None
    assert all(r["effective_price"] <= 100 for r in records)


def test_exact_name_search_end_to_end(ai, extractor, client):
    """The already-working behaviour must not regress."""
    router = StubRouter("product")
    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        response, _ = chat(client, "Show me Mechanical Keyboard", router, ai)
    assert response.status_code == 200
    body = response.json()
    route = body["debug"]["route_result"]
    assert route["found"] is True
    assert any("Mechanical Keyboard" in r["name"] for r in body["debug"]["records"])
    assert route["filters"]["search"] == "Mechanical Keyboard"


# ---------------------------------- product text matching (hyphens, plurals)
# Incident: "Show me Wireless Noise-Cancelling Headphones" returned found=false,
# count=0. The catalogue stores "Wireless Noise-Cancelling Headphones" but the
# extractor emitted "Wireless Noise Cancelling Headphones" (hyphen dropped), so
# LIKE '%Wireless Noise Cancelling Headphones%' could never match. Text matching
# is now punctuation-insensitive and token based, still entirely in SQL.
HEADPHONES = "Wireless Noise-Cancelling Headphones"


def _names(body):
    return [record["name"] for record in body["debug"]["records"]]


def test_exact_name_search_returns_only_that_product(ai, extractor, client):
    """A. The already-working exact search must keep working and stay narrow."""
    router = StubRouter("product")
    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        response, _ = chat(client, "Show me Mechanical Keyboard", router, ai)
    body = response.json()
    assert body["debug"]["route_result"]["found"] is True
    assert _names(body) == ["Mechanical Keyboard"]


@pytest.mark.parametrize("search", [
    HEADPHONES,                               # exactly as stored
    "Wireless Noise Cancelling Headphones",   # B/C: hyphen dropped by the extractor
    "wireless-noise-cancelling-headphones",   # hyphens only
    "WIRELESS NOISE CANCELLING HEADPHONES",   # case
    "wireless headphone",                     # singular
    "wireless headphones",                    # plural
    "noise cancelling headphones",            # partial, leading word dropped
    "wireless headphone you have",            # question wording
])
def test_product_search_ignores_punctuation_and_number(ai, extractor, client, search):
    """B/C/D. Punctuation, case, number and filler words must not block a match."""
    router = StubRouter("product")
    extractor.return_value.invoke_json.return_value["search"] = search
    response, _ = chat(client, f"Show me {search}", router, ai)
    body = response.json()
    assert HEADPHONES in _names(body), (search, body["debug"]["route_result"])
    assert body["debug"]["route_result"]["found"] is True


def test_question_wording_does_not_become_a_required_token(ai, extractor, client):
    """D. 'Do you have wireless headphones?' even when the extractor is down.

    Without the extractor the whole raw message becomes the search text, so the
    question words must not be treated as required keywords.
    """
    router = StubRouter("product")
    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        response, _ = chat(client, "Do you have wireless headphones?", router, ai)
    body = response.json()
    assert HEADPHONES in _names(body), body["debug"]["route_result"]


def test_partial_multi_word_search_finds_the_product(ai, extractor, client):
    """4. 'cotton t shirt' must reach "Classic Cotton T-Shirt"."""
    router = StubRouter("product")
    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        response, _ = chat(client, "Show me cotton t shirt", router, ai)
    assert _names(response.json()) == ["Classic Cotton T-Shirt"]


def test_keyword_search_stays_narrow(ai, extractor, client):
    """7. 'keyboard' must not return every Electronics product."""
    router = StubRouter("product")
    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        response, _ = chat(client, "keyboard", router, ai)
    names = _names(response.json())
    assert names == ["Mechanical Keyboard"], names


def test_search_and_price_ceiling_are_applied_together(ai, extractor, client):
    """E. search and max_price combine rather than replace one another."""
    router = StubRouter("product")

    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        response, _ = chat(client, "Show me wireless headphones under $100", router, ai)
    route = response.json()["debug"]["route_result"]
    assert route["filters"]["search"] == "wireless headphones"
    assert route["filters"]["max_price"] == 100
    # The only match costs $159.99, so the ceiling must exclude it.
    assert route["found"] is False and route["count"] == 0

    # ...and a matching product that is under the ceiling is still returned.
    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        response, _ = chat(client, "Show me cotton t shirt under $100", router, ai)
    body = response.json()
    assert body["debug"]["route_result"]["found"] is True
    assert _names(body) == ["Classic Cotton T-Shirt"]
    assert all(record["effective_price"] <= 100 for record in body["debug"]["records"])


def test_nonexistent_product_still_returns_found_false(ai, extractor, client):
    """F. Robust matching must not turn every query into a match."""
    router = StubRouter("product")
    extractor.return_value.invoke_json.return_value["search"] = "Quantum Flux Hoverboard"
    response, _ = chat(client, "Show me a quantum flux hoverboard", router, ai)
    body = response.json()
    assert body["debug"]["route_result"]["found"] is False
    assert body["debug"]["route_result"]["count"] == 0
    assert body["debug"]["records"] == []


def test_search_without_a_meaningful_word_matches_nothing(client):
    """Punctuation/single letters must not fall back to the whole catalogue.

    ``_clean_search`` already reduces a pure question ("do you have any?") to an
    empty search, which correctly means *no* text filter. This covers the layer
    below it: whatever reaches the query must not match everything either.
    """
    from app.ai.handlers import ProductQuery, search_products
    from tests.conftest import TestSession

    db = TestSession()
    try:
        assert search_products(db, ProductQuery(search="t")) == []
        assert search_products(db, ProductQuery(search="!!!")) == []
        assert search_products(db, ProductQuery(search="   ")) == []
        # ...while a real search on the same session still works.
        assert [r["name"] for r in search_products(db, ProductQuery(search="mechanical keyboard"))] \
            == ["Mechanical Keyboard"]
    finally:
        db.close()


def test_is_active_filter_still_applies_to_the_new_matcher(client):
    """8. Deactivating a row must hide it from the token matcher too."""
    from app.ai.handlers import ProductQuery, search_products
    from app.models import Product
    from tests.conftest import TestSession

    db = TestSession()
    try:
        keyboard = db.query(Product).filter(Product.name == "Mechanical Keyboard").one()
        keyboard.is_active = False
        db.commit()
        assert search_products(db, ProductQuery(search="keyboard")) == []
        # Other products are unaffected.
        assert [r["name"] for r in search_products(db, ProductQuery(search="wireless headphones"))] \
            == ["Wireless Noise-Cancelling Headphones"]
    finally:
        db.close()


def test_unknown_category_does_not_black_hole_the_search(client):
    """A category the catalogue does not have must be ignored, not enforced.

    The extractor sometimes reports a product *type* ("Headphones") as a
    category. Filtering on it returned zero rows even though the product was
    sitting in the catalogue under a different name.
    """
    from app.ai.handlers import ProductQuery, search_products
    from tests.conftest import TestSession

    db = TestSession()
    try:
        rows = search_products(db, ProductQuery(search="wireless headphones", category="Headphones"))
        assert [r["name"] for r in rows] == ["Wireless Noise-Cancelling Headphones"]
        # A category that really exists still filters, case-insensitively.
        assert all(r["category"] == "Shoes" for r in search_products(db, ProductQuery(category="shoes")))
    finally:
        db.close()


def test_hallucinated_category_is_ignored_end_to_end(ai, extractor, client):
    router = StubRouter("product")
    extractor.return_value.invoke_json.return_value.update(
        {"search": "wireless headphones", "category": "Headphones"}
    )
    response, _ = chat(client, "Show me wireless headphones", router, ai)
    body = response.json()
    assert _names(body) == ["Wireless Noise-Cancelling Headphones"]
    # The reported filter is still echoed so the response stays explainable.
    assert body["debug"]["route_result"]["filters"]["category"] == "Headphones"


def test_reported_filters_appear_even_when_nothing_matches(ai, extractor, client):
    """An empty result must still explain which filters produced it."""
    router = StubRouter("product")
    with patch("app.ai.handlers.get_groq_service", side_effect=RuntimeError("no key")):
        response, _ = chat(client, "products under $1", router, ai)
    route = response.json()["debug"]["route_result"]
    assert route["found"] is False
    assert route["filters"]["max_price"] == 1


# ----------------------------------------------------------- order route


def test_order_question_without_token_asks_for_login(ai, extractor, client):
    router = StubRouter("order")
    response, _ = chat(client, "where is my order?", router, ai)
    assert response.status_code == 200
    body = response.json()
    assert body["requires_auth"] is True
    assert body["debug"]["route_result"]["requires_auth"] is True


def test_order_question_with_token_returns_own_orders(ai, extractor, client, user_h):
    router = StubRouter("order")
    response, _ = chat(client, "where is my order?", router, ai, headers=user_h)
    assert response.status_code == 200
    body = response.json()
    assert body["requires_auth"] is False
    assert body["intent"] == "order"
    assert body["debug"]["records"], "seeded user should have at least one order"


def test_order_answer_never_leaks_another_users_orders(
    ai, extractor, client, user_h, user2_h
):
    """The core authorisation guarantee: Alice must not see Bob's orders."""
    router = StubRouter("order")
    as_alice, _ = chat(client, "show all my orders", router, ai, headers=user_h)
    as_bob, _ = chat(client, "show all my orders", router, ai, headers=user2_h)

    alice_orders = {o["id"] for o in as_alice.json()["debug"]["records"]}
    bob_orders = {o["id"] for o in as_bob.json()["debug"]["records"]}
    assert alice_orders, "fixture should give Alice an order"
    assert bob_orders, "fixture should give Bob an order"
    assert not (alice_orders & bob_orders), "users must not share order visibility"


def test_invalid_token_degrades_to_anonymous_not_500(ai, extractor, client):
    router = StubRouter("order")
    response, _ = chat(client, "where is my order?", router, ai,
                       headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 200
    assert response.json()["requires_auth"] is True


def test_requires_auth_means_this_request_was_unauthenticated(ai, extractor, client, user_h):
    """Documented semantics (deliberately unchanged).

    ``requires_auth`` is *not* a static property of the order route - it reports
    that THIS request arrived without a usable identity, so the response can
    tell the frontend to prompt for login. A signed-in request on the very same
    route must report False.
    """
    router = StubRouter("order")
    anonymous, _ = chat(client, "where is my order?", router, ai)
    signed_in, _ = chat(client, "where is my order?", router, ai, headers=user_h)

    assert anonymous.json()["route"] == "order", "the route is order either way"
    assert anonymous.json()["requires_auth"] is True
    assert signed_in.json()["requires_auth"] is False
    assert signed_in.json()["sources"] == ["mysql:orders"]


# ------------------------------------- order final answer (end to end)
# These deliberately do NOT stub generate_answer, so the real
# context -> prompt -> answer flow runs against the seeded database.

REFUSAL_ANSWER = (
    "I'm sorry, but I don't have that information. Could you let me know your "
    "order number, or you can reach out to our support team for help."
)


def chat_with_llm(client, message, router, ai, llm_answer, headers=None):
    """Run the real context -> prompt -> answer flow, controlling only the LLM.

    ``ai`` stubs ``generate_answer``; it is re-patched to the real function here
    because these tests are specifically about that flow. The LLM seam is
    ``app.ai.context_builder.get_groq_service`` - patching the router's copy
    would let a real network call escape.
    """
    return chat_with_real_answer(client, message, router, ai, headers, llm_answer)


def chat_with_real_answer(client, message, router, ai, headers, llm_answer=None, llm_error=None):
    from app.ai.context_builder import generate_answer as real_generate_answer

    with patch(f"{ROUTER_NAMESPACE}.get_router", return_value=router), patch(
        f"{ROUTER_NAMESPACE}.generate_answer", real_generate_answer
    ), patch("app.ai.context_builder.get_groq_service") as groq:
        groq.return_value.invoke.side_effect = llm_error
        groq.return_value.invoke.return_value = llm_answer
        groq.return_value.invoke_json.return_value = {
            "search": None, "category": None, "max_price": None, "order_id": None,
        }
        return client.post("/api/chat", json={"message": message}, headers=headers or {})


def place_extra_order(client, headers, product_id, quantity=1):
    """Give a seeded user more orders through the public API, so the
    multiple-orders path is exercised against real rows."""
    shipping = {
        "full_name": "Test User", "address": "1 Main St", "city": "Ludhiana",
        "postal_code": "141001", "phone": "9999999999",
    }
    added = client.post("/api/cart/items",
                        json={"product_id": product_id, "quantity": quantity},
                        headers=headers)
    assert added.status_code in (200, 201), added.text
    placed = client.post("/api/orders", json={"shipping": shipping}, headers=headers)
    assert placed.status_code == 201, placed.text
    return placed.json()["id"]


def test_where_is_my_order_answers_with_real_statuses(ai, extractor, client, user_h):
    """A. Multiple orders: a refusal must be replaced by the actual statuses."""
    place_extra_order(client, user_h, 2)
    place_extra_order(client, user_h, 3)

    router = StubRouter("order")
    response = chat_with_llm(client, "Where is my order?", router, ai,
                             REFUSAL_ANSWER, headers=user_h)
    assert response.status_code == 200
    body = response.json()

    assert body["route"] == "order"
    assert body["sources"] == ["mysql:orders"]
    records = body["debug"]["records"]
    assert len(records) >= 2, "fixture should give the user several orders"

    answer = body["answer"]
    assert REFUSAL_ANSWER not in answer
    assert "don't have that information" not in answer.lower()
    for record in records:
        assert f"Order #{record['id']}" in answer
        assert record["status"] in answer


def test_specific_order_status_is_answered(ai, extractor, client, user_h):
    """B. 'What is the status of order #N?' must state that order's status."""
    router = StubRouter("order")

    # Discover an order this user actually owns.
    seed = chat_with_llm(client, "Where is my order?", router, ai, REFUSAL_ANSWER,
                         headers=user_h).json()
    record = seed["debug"]["records"][0]

    response = chat_with_llm(client, f"What is the status of order #{record['id']}?",
                             router, ai, REFUSAL_ANSWER, headers=user_h)
    body = response.json()
    assert body["debug"]["route_result"]["found"] is True
    assert f"Order #{record['id']}" in body["answer"]
    assert record["status"] in body["answer"]


def test_latest_order_question_uses_the_newest_order(ai, extractor, client, user_h):
    """C. 'latest' is the first (newest) retrieved order."""
    place_extra_order(client, user_h, 2)
    router = StubRouter("order")
    response = chat_with_llm(client, "What is the status of my latest order?", router,
                             ai, REFUSAL_ANSWER, headers=user_h)
    body = response.json()
    records = body["debug"]["records"]
    newest = records[0]

    assert body["debug"]["route_result"]["found"] is True
    assert f"Order #{newest['id']}" in body["answer"]
    assert newest["status"] in body["answer"]
    if len(records) > 1:
        assert body["answer"].index(f"Order #{newest['id']}") < body["answer"].index(
            f"Order #{records[-1]['id']}"
        ), "most recent order must be listed first"


def test_order_answer_invents_no_tracking_details(ai, extractor, client, user_h):
    """Anti-fabrication: nothing that is not in the order rows."""
    router = StubRouter("order")
    answer = chat_with_llm(client, "Where is my order?", router, ai, REFUSAL_ANSWER,
                           headers=user_h).json()["answer"].lower()
    for banned in ("tracking number", "courier", "fedex", "ups", "delivered on",
                   "will arrive", "out for delivery"):
        assert banned not in answer


def test_good_llm_answer_is_not_overwritten(ai, extractor, client, user_h):
    """The grounding guard must not clobber a correct model answer."""
    router = StubRouter("order")
    good = "Your most recent order was delivered."
    response = chat_with_llm(client, "Where is my order?", router, ai, good,
                             headers=user_h)
    assert response.json()["answer"] == good


def test_order_answer_survives_llm_error(ai, extractor, client, user_h):
    router = StubRouter("order")
    response = chat_with_real_answer(
        client, "Where is my order?", router, ai, user_h,
        llm_error=RuntimeError("groq down"),
    )
    body = response.json()
    assert body["debug"]["route_result"]["found"] is True
    assert body["sources"] == ["mysql:orders"]
    assert f"Order #{body['debug']['records'][0]['id']}" in body["answer"]


def test_order_answer_with_no_orders_keeps_the_existing_fallback(ai, extractor, client, user_h):
    """D. No orders: the previous FALLBACK_ANSWER behaviour is preserved."""
    from app.ai.context_builder import generate_answer as real_generate_answer
    from app.ai.handlers import RouteContext
    from app.ai.prompts import FALLBACK_ANSWER

    empty = RouteContext(route="order", found=False, notes=["No orders were found."])
    router = StubRouter("order")
    with patch(f"{ROUTER_NAMESPACE}.get_router", return_value=router), patch(
        f"{ROUTER_NAMESPACE}.order_handler", return_value=empty
    ), patch(f"{ROUTER_NAMESPACE}.generate_answer", real_generate_answer), patch(
        "app.ai.context_builder.get_groq_service"
    ) as groq:
        groq.return_value.invoke.return_value = REFUSAL_ANSWER
        groq.return_value.invoke_json.return_value = {
            "search": None, "category": None, "max_price": None, "order_id": None,
        }
        response = client.post("/api/chat", json={"message": "Where is my order?"},
                               headers=user_h)

    body = response.json()
    assert body["debug"]["route_result"]["found"] is False
    assert body["sources"] == [], "no orders means no mysql source"
    assert body["answer"] == FALLBACK_ANSWER
    assert groq.return_value.invoke.call_count == 0, "no LLM call without context"


def test_order_answers_stay_scoped_to_the_asking_user(ai, extractor, client, user_h, user2_h):
    """E. Neither the records nor the answer may cross users."""
    router = StubRouter("order")
    alice = chat_with_llm(client, "Where is my order?", router, ai, REFUSAL_ANSWER,
                          headers=user_h).json()
    bob = chat_with_llm(client, "Where is my order?", router, ai, REFUSAL_ANSWER,
                        headers=user2_h).json()

    alice_ids = {o["id"] for o in alice["debug"]["records"]}
    bob_ids = {o["id"] for o in bob["debug"]["records"]}
    assert alice_ids and bob_ids
    assert not alice_ids & bob_ids

    for answer, mine in ((alice["answer"], alice_ids), (bob["answer"], bob_ids)):
        assert REFUSAL_ANSWER not in answer
        for order_id in re.findall(r"Order #(\d+)", answer):
            assert int(order_id) in mine


# ----------------------------------------------------------- confidence gate


def test_low_confidence_clarifies_without_touching_data_sources(ai, client):
    router = StubRouter("rag", confidence=0.42)
    response, retrieve_mock = chat(client, "hmm what about ...", router, ai)
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "clarification"
    assert retrieve_mock.called is False, "low confidence must not reach Qdrant"
    assert router.clarified == ["hmm what about ..."]


def test_unknown_intent_clarifies(ai, client):
    router = StubRouter("unknown", confidence=0.3)
    response, retrieve_mock = chat(client, "asdfgh qwerty", router, ai)
    assert response.status_code == 200
    assert response.json()["route"] == "clarification"
    assert retrieve_mock.called is False


# ----------------------------------------------------------- input validation


def test_empty_message_is_rejected(ai, client):
    router = StubRouter("rag")
    with patch(f"{ROUTER_NAMESPACE}.get_router", return_value=router):
        response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_whitespace_only_message_is_rejected(ai, client):
    router = StubRouter("rag")
    with patch(f"{ROUTER_NAMESPACE}.get_router", return_value=router):
        response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code in (400, 422)


def test_oversized_message_is_rejected(ai, client):
    router = StubRouter("rag")
    with patch(f"{ROUTER_NAMESPACE}.get_router", return_value=router):
        response = client.post("/api/chat", json={"message": "x" * 5000})
    assert response.status_code == 400
    assert "too long" in response.json()["error"]["message"].lower()


# ----------------------------------------------------------- configuration errors


def test_missing_groq_key_returns_useful_503(ai, client):
    unconfigured = AIConfig(groq_api_key="")
    router = StubRouter("rag")
    with patch(f"{ROUTER_NAMESPACE}.get_ai_config", return_value=unconfigured), patch(
        f"{ROUTER_NAMESPACE}.get_router", return_value=router
    ):
        response = client.post("/api/chat", json={"message": "what is your return policy?"})
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "AI_NOT_CONFIGURED"
    assert "GROQ_API_KEY" in body["detail"]


def test_product_route_still_works_without_qdrant_and_hf(ai, extractor, client):
    """Only the RAG route needs embeddings + Qdrant."""
    groq_only = AIConfig(groq_api_key="gsk_test")
    router = StubRouter("product")
    with patch(f"{ROUTER_NAMESPACE}.get_ai_config", return_value=groq_only), patch(
        f"{ROUTER_NAMESPACE}.get_router", return_value=router
    ):
        response = client.post("/api/chat", json={"message": "do you sell laptops?"})
    assert response.status_code == 200, response.text


def test_rag_route_without_qdrant_returns_useful_503(ai, client):
    groq_only = AIConfig(groq_api_key="gsk_test")
    router = StubRouter("rag")
    with patch(f"{ROUTER_NAMESPACE}.get_ai_config", return_value=groq_only), patch(
        f"{ROUTER_NAMESPACE}.get_router", return_value=router
    ):
        response = client.post("/api/chat", json={"message": "what is your return policy?"})
    assert response.status_code == 503
    detail = response.json()["error"]["detail"]
    assert "QDRANT_URL" in detail and "HF_API_KEY" in detail


# ----------------------------------------------------------- health


def test_health_reports_capabilities_without_secrets(ai, client):
    response = client.get("/api/chat/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert body["model"] == CONFIGURED.groq_model
    assert body["embedding_model"] == CONFIGURED.hf_embedding_model
    blob = json.dumps(body)
    assert "gsk_test" not in blob
    assert "hf_test" not in blob
    assert "qd_test" not in blob


def test_health_is_public(ai, client):
    assert client.get("/api/chat/health").status_code == 200
