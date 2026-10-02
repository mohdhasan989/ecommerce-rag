"""Context builder + final answer generation.

Normalises whichever route ran (RAG chunks, MySQL products, MySQL orders) into a
single, clearly-labelled text block for the LLM. Unrelated data is never mixed:
only the selected route's context is included.

Grounding rules live in ``app.ai.prompts.ANSWER_SYSTEM``: use the context, never
invent products/orders/policies, and admit when the context is insufficient.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.ai.config import get_ai_config
from app.ai.handlers import RouteContext
from app.ai.llm.groq_client import get_groq_service
from app.ai.prompts import ANSWER_SYSTEM, FALLBACK_ANSWER, ORDER_ANSWER_SYSTEM
from app.ai.rag.retriever import RetrievalResult
from app.ai.router.intent_router import Intent, RouteDecision

log = logging.getLogger("app.ai.context")

__all__ = ["AnswerContext", "build_context", "generate_answer", "format_rag_context",
           "format_product_context", "format_order_context", "build_order_answer",
           "looks_ungrounded"]

MAX_CONTEXT_CHARS = 8000


@dataclass
class AnswerContext:
    """Normalised context handed to the final LLM call."""

    route: str
    text: str
    has_context: bool = False
    sources: list[str] = None  # type: ignore[assignment]
    # Rendered directly from the retrieved rows. Used only when the model
    # ignores a populated context; empty for every other route.
    grounded_answer: str = ""

    def __post_init__(self):
        if self.sources is None:
            self.sources = []

    def as_dict(self) -> dict:
        return {
            "route": self.route,
            "has_context": self.has_context,
            "char_count": len(self.text),
            "sources": self.sources,
        }


def _clip(text: str) -> str:
    return text if len(text) <= MAX_CONTEXT_CHARS else text[:MAX_CONTEXT_CHARS] + "\n[truncated]"


# ---------------------------------------------------------------- builders


def format_rag_context(retrieval: RetrievalResult) -> tuple[str, list[str]]:
    if retrieval.is_empty:
        return "No documents were retrieved for this question.", []
    blocks, sources = [], []
    for index, chunk in enumerate(retrieval.chunks, start=1):
        origin = chunk.metadata.get("source") or "unknown"
        page = chunk.metadata.get("page")
        where = f"{origin}" + (f", page {page}" if page else "")
        score = f"{chunk.score:.3f}" if chunk.score is not None else "n/a"
        blocks.append(f"[Passage {index} | source: {where} | similarity: {score}]\n{chunk.text}")
        if where not in sources:
            sources.append(where)
    return _clip("STORE DOCUMENTS:\n\n" + "\n\n---\n\n".join(blocks)), sources


def format_product_context(context: RouteContext) -> tuple[str, list[str]]:
    if not context.data:
        notes = " ".join(context.notes) or "No matching products were found."
        return f"PRODUCT CATALOGUE:\n{notes}", []
    blocks = []
    for product in context.data:
        price = product["effective_price"]
        price_text = f"${price:,.2f}"
        if product.get("discount_price") is not None:
            price_text += f" (discounted from ${product['price']:,.2f})"
        stock = (
            "out of stock" if not product["in_stock"]
            else f"{product['stock']} in stock"
        )
        blocks.append(
            f"- {product['name']} (SKU {product['sku']})\n"
            f"  brand: {product.get('brand') or 'n/a'} | category: {product.get('category') or 'n/a'}\n"
            f"  price: {price_text} | availability: {stock}\n"
            f"  description: {product.get('description') or 'n/a'}"
        )
    return _clip("PRODUCT CATALOGUE:\n" + "\n".join(blocks)), ["mysql:products"]


def format_order_context(context: RouteContext) -> tuple[str, list[str]]:
    if context.extra.get("requires_auth"):
        return (
            "ORDER SYSTEM:\nNo orders could be read: the customer is not signed in.",
            [],
        )
    if not context.data:
        notes = " ".join(context.notes) or "No orders were found."
        return f"ORDER SYSTEM:\n{notes}", []
    blocks = []
    for order in context.data:
        items = ", ".join(
            f"{item['name']} x{item['quantity']} (${item['subtotal']:,.2f})"
            for item in order["items"]
        )
        blocks.append(
            f"- Order #{order['id']} | status: {order['status']} | "
            f"total: ${order['total_amount']:,.2f} | placed: {order['created_at']}\n"
            f"  items: {items or 'none'}\n"
            f"  ships to: {order.get('city') or 'n/a'}"
        )
    header = (
        "ORDER SYSTEM:\n"
        "The following are the signed-in customer's own orders, most recent first.\n"
        "Every id, status, item, amount and city below is a verified fact.\n\n"
    )
    return _clip(header + "\n".join(blocks)), ["mysql:orders"]


# Phrases that mean "the model decided it had nothing", even though the context
# held real records. Used to catch an ungrounded answer before shipping it.
UNGROUNDED_MARKERS = (
    "don't have that information",
    "do not have that information",
    "don't have this information",
    "do not have this information",
    "don't have your order",
    "cannot find",
    "can't find",
    "could not find",
    "couldn't find",
    "unable to find",
    "not able to find",
    "no information about",
    "let me know your order number",
    "provide your order number",
    "share your order number",
    "reach out to our support",
    "contact our support team",
)


def looks_ungrounded(answer: str) -> bool:
    """True when an answer claims to lack information we actually supplied."""
    lowered = (answer or "").lower()
    return any(marker in lowered for marker in UNGROUNDED_MARKERS)


def build_order_answer(orders: list[dict]) -> str:
    """Deterministic summary straight from the retrieved order rows.

    Used when the model answers (or fails) in a way that ignores the context, so
    a populated order context can never produce "I don't have that information".
    """
    if not orders:
        return ""
    lines = []
    for order in orders:
        names = ", ".join(str(item["name"]) for item in order.get("items") or [])
        lines.append(
            f"Order #{order['id']} - {order['status']} - "
            f"{names or 'no items recorded'} - ${order['total_amount']:,.2f}"
        )
    if len(lines) == 1:
        lead = "Here is your order:"
    else:
        lead = f"You have {len(lines)} orders, most recent first:"
    return f"{lead}\n" + "\n".join(lines)


def build_context(
    *,
    decision: RouteDecision,
    retrieval: RetrievalResult | None = None,
    route_context: RouteContext | None = None,
) -> AnswerContext:
    """Turn a completed route into one prompt-ready context block."""
    if decision.intent == Intent.RAG and retrieval is not None:
        text, sources = format_rag_context(retrieval)
        return AnswerContext(route="rag", text=text, has_context=not retrieval.is_empty, sources=sources)
    if decision.intent == Intent.PRODUCT and route_context is not None:
        text, sources = format_product_context(route_context)
        return AnswerContext(route="product", text=text, has_context=bool(route_context.data), sources=sources)
    if decision.intent == Intent.ORDER and route_context is not None:
        text, sources = format_order_context(route_context)
        return AnswerContext(
            route="order",
            text=text,
            has_context=bool(route_context.data),
            sources=sources,
            grounded_answer=build_order_answer(route_context.data),
        )
    return AnswerContext(route=decision.intent, text="No context was retrieved.", has_context=False)


# ---------------------------------------------------------------- answering


def generate_answer(question: str, context: AnswerContext) -> str:
    """Final grounded answer from Groq, or a safe fallback when ungrounded."""
    if not context.has_context:
        log.info("No usable context for route=%s; returning fallback", context.route)
        return FALLBACK_ANSWER

    # The order route gets a prompt that treats its context as authoritative.
    template = ORDER_ANSWER_SYSTEM if context.route == "order" else ANSWER_SYSTEM
    system = template.replace("{context}", context.text)
    try:
        answer = get_groq_service().invoke(system, question)
    except Exception as exc:  # noqa: BLE001 - answer must never 500
        log.warning("Answer generation failed (%s)", type(exc).__name__)
        answer = ""

    # A populated order context must never degrade into "I don't have that
    # information", so fall back to the rows themselves rather than a refusal.
    if context.grounded_answer and (not answer or looks_ungrounded(answer)):
        log.info("Order answer was ungrounded; using the retrieved order records")
        return context.grounded_answer
    return answer or FALLBACK_ANSWER


def debug_dump(context: AnswerContext) -> str:
    return json.dumps(context.as_dict(), indent=2)