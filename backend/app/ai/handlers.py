"""Route handlers for the product and order intents.

Both read from the **existing** MySQL database through the existing SQLAlchemy
models/services. No product or order data is ever written to Qdrant.

Security note (order route): the LLM may only ever suggest *which* of the
authenticated user's own orders to talk about. The user id always comes from the
JWT-authenticated principal in the request, never from model output.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.ai.llm.groq_client import get_groq_service
from app.models import Order, OrderStatus, Product

log = logging.getLogger("app.ai.handlers")

__all__ = [
    "RouteContext",
    "ProductQuery",
    "OrderQuery",
    "product_handler",
    "order_handler",
    "search_products",
    "list_user_orders",
]

PRODUCT_EXTRACT_SYSTEM = """Extract a product search from the customer's message.
Output raw JSON only:
{"search": "<keywords or empty>", "max_price": <number or null>, "category": "<category name or empty>"}

Use an empty string / null when the message does not state it. Never invent a
category name that is not a plain noun from the message."""

ORDER_EXTRACT_SYSTEM = """Extract an order reference from the customer's message.
Output raw JSON only: {"order_id": <integer or null>}
Use null unless the message contains an explicit order number (e.g. "order 12",
"#12"). Never guess a number. Never produce a user id or any other identifier."""

ORDER_ID_PATTERN = re.compile(r"(?:#|order\s*(?:id\s*)?|ord\s*)(\d{1,12})", re.IGNORECASE)

# ------------------------------------------------------------------ prices
# A bare number is NOT a budget: "Show me iPhone 15" must not become
# max_price=15. A ceiling only counts when the message says so, either with a
# comparative ("under", "below", "less than", ...) or by naming a currency.
MAX_PRICE_PATTERN = re.compile(
    r"(?:under|below|beneath|less\s+than|lower\s+than|cheaper\s+than|at\s+most"
    r"|no\s+more\s+than|up\s+to|within|max(?:imum)?|below\s+or\s+equal\s+to)"
    r"\s*(?:only\s*)?(?:about\s*)?(?:around\s*)?(?:cheapest\s*)?"
    r"(?P<currency>[$₹€£]|(?:rs\.?|inr|usd)\b)?\s*"
    # Grouped digits first ("1,250", "1,25,000"), then a plain run ("50000").
    r"(?P<amount>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*(?P<thousands>[kK])?"
    r"(?:\s*(?:usd|inr|dollars?|rupees?|bucks?))?",
    re.IGNORECASE,
)

# "$250", "Rs 250" with no comparative still reads as a ceiling.
BARE_PRICE_PATTERN = re.compile(
    r"(?P<currency>[$₹€£])\s*"
    r"(?P<amount>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*(?P<thousands>[kK])?"
    r"(?:\s*(?:usd|inr|dollars?|rupees?))?"
)

# A comparative with no digits ("under one dollar") still must not end up
# inside the keyword search.
PRICE_TAIL_PATTERN = re.compile(
    r"\b(?:under|below|beneath|less\s+than|lower\s+than|cheaper\s+than|at\s+most"
    r"|no\s+more\s+than|up\s+to|within|max(?:imum)?)\b.*$",
    re.IGNORECASE,
)

# Politeness/plurality words around the real keyword(s). Stripped from the
# *edges* only, so "Mechanical Keyboard" and multi-word names survive intact.
SEARCH_FILLER_WORDS = frozenset(
    {
        "show", "me", "us", "all", "any", "some", "please", "pls", "find",
        "list", "give", "get", "search", "display", "see", "view", "want",
        "need", "looking", "look", "for", "i", "we", "do", "you", "have",
        "has", "there", "is", "are", "the", "a", "an", "of", "and", "with",
        "in", "that", "this", "products", "product", "items", "item", "goods",
        "stuff", "available", "stock", "sell", "sells", "selling", "offer",
        "offers", "under", "below", "beneath", "less", "than", "lower",
        "cheaper", "up", "to", "at", "most", "max", "maximum", "min", "only",
        "just", "about", "around", "roughly", "approximately", "or", "equal",
        "to", "no", "more", "than", "less", "priced", "costing", "rs", "inr",
        "usd", "dollar", "dollars", "rupee", "rupees",
        "anything", "everything", "something", "nothing", "cheapest",
    }
)


@dataclass
class RouteContext:
    """Normalised result of whichever route the router selected."""

    route: str
    found: bool = True
    data: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "route": self.route,
            "found": self.found,
            "count": len(self.data),
            "notes": self.notes,
            **self.extra,
        }


# ---------------------------------------------------------------- products


@dataclass
class ProductQuery:
    search: str = ""
    max_price: float | None = None
    category: str = ""


def _product_row(product: Product) -> dict:
    effective = product.discount_price if product.discount_price is not None else product.price
    return {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "sku": product.sku,
        "category": product.category_name,
        "description": product.description,
        "price": float(product.price),
        "discount_price": float(product.discount_price) if product.discount_price is not None else None,
        "effective_price": float(effective),
        "in_stock": product.stock > 0,
        "stock": product.stock,
    }


def search_products(db: Session, query: ProductQuery, limit: int = 5) -> list[dict]:
    """Reuse the MySQL catalogue. Applies active-only, price and text filters."""
    statement = db.query(Product).filter(Product.is_active.is_(True))

    if query.search:
        like = f"%{query.search}%"
        statement = statement.filter(
            or_(Product.name.like(like), Product.brand.like(like), Product.description.like(like))
        )
    if query.max_price is not None:
        statement = statement.filter(
            func.coalesce(Product.discount_price, Product.price) <= query.max_price
        )
    if query.category:
        statement = statement.filter(Product.category.has(name=query.category))

    products = statement.order_by(Product.id).limit(max(1, limit)).all()
    return [_product_row(product) for product in products]


def _amount_to_float(match: re.Match) -> float | None:
    try:
        # "1,250" / "1,25,000" -> 1250 / 125000
        amount = float(match.group("amount").replace(",", ""))
    except (AttributeError, TypeError, ValueError):
        return None
    if match.groupdict().get("thousands"):
        amount *= 1000
    return amount if amount > 0 else None


def _extract_max_price(message: str) -> tuple[float | None, str]:
    """Return ``(max_price, message_without_price_phrase)``.

    Only an explicit ceiling is read as a budget; the matched phrase is cut out
    of the message so it cannot leak into the keyword search.
    """
    for pattern in (MAX_PRICE_PATTERN, BARE_PRICE_PATTERN):
        match = pattern.search(message)
        if not match:
            continue
        amount = _amount_to_float(match)
        if amount is not None:
            remainder = (message[: match.start()] + " " + message[match.end() :]).strip()
            return amount, remainder
    # Comparative present but no digits: still drop the trailing phrase.
    return None, PRICE_TAIL_PATTERN.sub("", message).strip()


def _clean_search(raw: str) -> str:
    """Strip filler from the edges, collapsing an all-filler phrase to ``""``.

    "Show me Mechanical Keyboard" -> "Mechanical Keyboard"
    "Show me products"           -> ""            (no keyword filter)
    """
    tokens = [token for token in re.split(r"[^\w]+", raw or "", flags=re.UNICODE) if token]
    while tokens and tokens[0].lower() in SEARCH_FILLER_WORDS:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in SEARCH_FILLER_WORDS:
        tokens.pop()
    return " ".join(tokens)[:120]


def _regex_product_query(message: str) -> ProductQuery:
    """Deterministic filters from the raw message: no LLM involved."""
    max_price, remainder = _extract_max_price(message or "")
    return ProductQuery(search=_clean_search(remainder), max_price=max_price)


def _parse_product_query(message: str) -> ProductQuery:
    """Structured filters for the product route.

    The extraction LLM stays the primary source of the keyword and category, but
    two rules keep it from breaking plain price questions:

    1. An *explicitly empty* search is trusted. The model answering "no
       keywords" means "do not filter by name" -- substituting the raw message
       instead turns "under $100" into ``LIKE '%under $100%'``, which matches
       nothing and silently hides a working price filter.
    2. A price stated in the message always sets ``max_price``, so a model that
       omits (or misreads) the figure cannot drop the ceiling.

    The regex scan doubles as the fallback when the LLM is unavailable.
    """
    message = (message or "").strip()
    query = _regex_product_query(message)

    try:
        data = get_groq_service().invoke_json(PRODUCT_EXTRACT_SYSTEM, message)
    except Exception:  # noqa: BLE001 - extraction is best effort, regex fallback wins
        log.info("Product extraction unavailable; using regex product filters")
        return query
    if not isinstance(data, dict):
        return query

    search = _clean_search(str(data.get("search") or ""))
    if search:
        query.search = search

    category = str(data.get("category") or "").strip()
    if category:
        query.category = category[:60]

    raw_price = data.get("max_price")
    if isinstance(raw_price, (int, float)) and not isinstance(raw_price, bool):
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            price = 0.0
        if price > 0:
            query.max_price = price
    return query


def product_handler(db: Session, message: str, limit: int = 5) -> RouteContext:
    """Answer a catalogue question from MySQL."""
    query = _parse_product_query(message)
    products = search_products(db, query, limit=limit)
    context = RouteContext(route="product", found=bool(products), data=products)
    # Always report the filters that were applied. When a filter is wrong the
    # empty result is otherwise impossible to explain from the response alone.
    context.extra["filters"] = {
        "search": query.search or None,
        "max_price": query.max_price,
        "category": query.category or None,
    }
    if not products:
        context.notes.append("No matching products in the catalogue.")
    return context


# ------------------------------------------------------------------ orders


@dataclass
class OrderQuery:
    order_id: int | None = None


def _order_row(order: Order) -> dict:
    address = {}
    if order.shipping_address:
        try:
            import json

            address = json.loads(order.shipping_address)
        except (TypeError, ValueError):
            address = {}
    return {
        "id": order.id,
        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        "total_amount": float(order.total_amount),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "city": address.get("city") or "",
        "items": [
            {"name": item.product_name, "quantity": item.quantity, "subtotal": float(item.subtotal)}
            for item in order.items
        ],
        "item_count": sum(item.quantity for item in order.items),
    }


def list_user_orders(db: Session, user_id: int, order_id: int | None = None, limit: int = 5) -> list[dict]:
    """Orders for ONE authenticated user. ``user_id`` is never model-supplied."""
    statement = db.query(Order).filter(Order.user_id == user_id)
    if order_id is not None:
        statement = statement.filter(Order.id == order_id)
    orders = statement.order_by(Order.id.desc()).limit(max(1, limit)).all()
    return [_order_row(order) for order in orders]


def _parse_order_query(message: str) -> OrderQuery:
    query = OrderQuery()
    match = ORDER_ID_PATTERN.search(message or "")
    if match:
        try:
            query.order_id = int(match.group(1))
        except ValueError:
            query.order_id = None
        return query
    try:
        data = get_groq_service().invoke_json(ORDER_EXTRACT_SYSTEM, message)
    except Exception:  # noqa: BLE001 - extraction is best effort
        return query
    raw = data.get("order_id")
    if isinstance(raw, int) and raw > 0:
        query.order_id = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        query.order_id = int(raw.strip())
    return query


def order_handler(db: Session, user: object | None, message: str, limit: int = 5) -> RouteContext:
    """Answer an order question from MySQL, scoped to the authenticated user."""
    if user is None:
        return RouteContext(
            route="order",
            found=False,
            notes=["You need to be logged in to ask about your orders."],
            extra={"requires_auth": True},
        )

    user_id = int(getattr(user, "id"))
    query = _parse_order_query(message)
    orders = list_user_orders(db, user_id, query.order_id, limit=limit)

    context = RouteContext(route="order", found=bool(orders), data=orders)
    context.extra["scoped_to_user_id"] = user_id
    if not orders:
        if query.order_id is not None:
            context.notes.append(
                f"No order #{query.order_id} was found on your account."
            )
        else:
            context.notes.append("No orders were found on your account.")
    return context


# ------------------------------------------------------------------ statuses

ORDER_STATUSES = tuple(status.value for status in OrderStatus)