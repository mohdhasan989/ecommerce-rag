"""LLM-based intent router with confidence gating.

    question -> Groq LLM -> {"intent": ..., "confidence": ...}

Intents: rag | product | order | unknown

Below ``ROUTER_CONFIDENCE_THRESHOLD`` the message is *not* dispatched to RAG (or
any data route). Instead a clarifying question is produced, which is the whole
point of the confidence check.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.ai.config import AIConfig, get_ai_config
from app.ai.exceptions import AIError, ConfigurationError
from app.ai.llm.groq_client import get_groq_service
from app.ai.prompts import CLARIFICATION_SYSTEM, INTENT_SYSTEM

log = logging.getLogger("app.ai.router")

__all__ = ["Intent", "RouteDecision", "IntentRouter", "get_router", "reset_router_cache"]

VALID_INTENTS = ("rag", "product", "order", "unknown")


class Intent:
    RAG = "rag"
    PRODUCT = "product"
    ORDER = "order"
    UNKNOWN = "unknown"


@dataclass
class RouteDecision:
    intent: str = Intent.UNKNOWN
    confidence: float = 0.0
    reason: str = ""
    threshold: float = 0.80

    @property
    def is_confident(self) -> bool:
        return self.confidence >= self.threshold

    @property
    def route(self) -> str:
        """Where the message should go: the intent, or ``clarification``."""
        if not self.is_confident:
            return "clarification"
        return self.intent

    @property
    def needs_clarification(self) -> bool:
        return self.route == "clarification"

    def as_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "route": self.route,
            "threshold": self.threshold,
        }


class IntentRouter:
    def __init__(self, config: AIConfig | None = None):
        self._config = config or get_ai_config()

    @property
    def threshold(self) -> float:
        return float(self._config.router_confidence_threshold)

    # ---------------- classification ----------------

    def classify(self, message: str) -> RouteDecision:
        """Ask the LLM to label the message.

        Configuration problems (e.g. a missing GROQ_API_KEY) propagate as
        ConfigurationError so the API can return a useful 503. Transient
        provider noise degrades to ``unknown`` instead of 500-ing the chat route.
        """
        message = (message or "").strip()
        if not message:
            return RouteDecision(
                intent=Intent.UNKNOWN, confidence=1.0,
                reason="empty message", threshold=self.threshold,
            )
        try:
            data = get_groq_service().invoke_json(INTENT_SYSTEM, message)
        except ConfigurationError:
            raise  # missing API key / model: caller surfaces a clear 503
        except AIError as exc:
            log.warning("Intent classification unavailable (%s); defaulting to unknown", type(exc).__name__)
            return RouteDecision(
                intent=Intent.UNKNOWN, confidence=0.0,
                reason="classification unavailable", threshold=self.threshold,
            )
        except Exception as exc:  # noqa: BLE001 - never 500 the chat route
            log.warning("Intent classification failed (%s); defaulting to unknown", type(exc).__name__)
            return RouteDecision(
                intent=Intent.UNKNOWN, confidence=0.0,
                reason="classification unavailable", threshold=self.threshold,
            )

        intent = str(data.get("intent") or "").strip().lower()
        if intent not in VALID_INTENTS:
            intent = Intent.UNKNOWN
        confidence = self._coerce_confidence(data.get("confidence"))
        reason = str(data.get("reason") or "")[:120]
        return RouteDecision(
            intent=intent, confidence=confidence, reason=reason, threshold=self.threshold
        )

    @staticmethod
    def _coerce_confidence(value: object) -> float:
        """Accept 0.91, "0.91", "91%" or 91 and normalise to 0..1."""
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, (int, float)):
            number = float(value)
            return max(0.0, min(1.0, number if number <= 1.0 else number / 100.0))
        if isinstance(value, str):
            text = value.strip().rstrip("%")
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if match:
                number = float(match.group())
                return max(0.0, min(1.0, number if number <= 1.0 else number / 100.0))
        return 0.0

    # ---------------- clarification ----------------

    def clarification(self, message: str, decision: RouteDecision) -> str:
        """Produce a clarifying question for a low-confidence message."""
        try:
            data = get_groq_service().invoke_json(
                CLARIFICATION_SYSTEM,
                f"Customer message: {message}\n"
                f"Best-guess intent: {decision.intent} (confidence {decision.confidence:.2f})",
            )
            text = str(data.get("clarification") or "").strip()
            if text:
                return text[:300]
        except ConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Clarification generation failed (%s)", type(exc).__name__)
        from app.ai.prompts import CLARIFICATION_FALLBACK

        return CLARIFICATION_FALLBACK


_ROUTER: IntentRouter | None = None


def get_router() -> IntentRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = IntentRouter()
    return _ROUTER


def reset_router_cache() -> None:
    global _ROUTER
    _ROUTER = None