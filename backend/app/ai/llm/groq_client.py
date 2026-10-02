"""Groq LLM service.

One reusable, centrally configured client shared by both consumers required by
the spec:

    1. the intent router
    2. final RAG response generation

The API key and model are read from ``app.config.Settings`` via ``app.ai.config``
-- never hardcoded, never logged.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.ai.config import AIConfig, get_ai_config
from app.ai.exceptions import ConfigurationError, LLMError, safe_provider_error

log = logging.getLogger("app.ai.groq")

__all__ = ["GroqService", "get_llm", "get_groq_service", "reset_llm_cache"]

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _is_auth_failure(exc: BaseException) -> bool:
    """True when the provider rejected our credentials.

    Cheaper and more reliable than importing groq's exception hierarchy: the
    official SDK puts the HTTP status on the exception, and LangChain re-raises
    it unchanged.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if status in (401, 403):
        return True
    name = type(exc).__name__.lower()
    if "authentication" in name or "permission" in name:
        return True
    text = str(exc).lower()
    return "401" in text or "invalid api key" in text or "unauthorized" in text


class GroqService:
    """Thin wrapper over ``ChatGroq`` with JSON coercion and safe errors."""

    def __init__(self, config: AIConfig | None = None, llm: ChatGroq | None = None):
        self._config = config or get_ai_config()
        self._llm = llm

    # ---------------- configuration ----------------

    @property
    def model(self) -> str:
        return self._config.groq_model

    @property
    def llm(self) -> ChatGroq:
        if self._llm is None:
            if not self._config.groq_api_key.strip():
                raise ConfigurationError(self._config.missing("groq"), "groq")
            self._llm = ChatGroq(
                api_key=self._config.groq_api_key,
                model=self._config.groq_model,
                temperature=self._config.groq_temperature,
                max_tokens=self._config.groq_max_tokens,
            )
        return self._llm

    # ---------------- generation ----------------

    def invoke(self, system: str, user: str) -> str:
        """Plain text completion."""
        try:
            message = self.llm.invoke(
                [SystemMessage(content=system), HumanMessage(content=user)]
            )
        except ConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider raises many types
            log.error(safe_provider_error(exc, "groq"))
            if _is_auth_failure(exc):
                # A rejected key is a misconfiguration, not a transient blip:
                # retrying or degrading to a clarification would just hide it.
                raise ConfigurationError(
                    "GROQ_API_KEY",
                    "groq",
                    "The configured Groq API key was rejected (401). "
                    "Check that GROQ_API_KEY is valid and active.",
                ) from exc
            raise LLMError(
                "The assistant is temporarily unavailable. Please try again."
            ) from exc
        content = getattr(message, "content", "") or ""
        if isinstance(content, list):  # some providers return content blocks
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        return str(content).strip()

    def ping(self) -> bool:
        """Cheapest possible round trip, used by the health endpoint.

        Returns False for transient/transport problems but re-raises credential
        problems, so callers can tell "unreachable" from "bad key".
        """
        try:
            self.llm.invoke([HumanMessage(content="ping")])
            return True
        except ConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001
            if _is_auth_failure(exc):
                raise ConfigurationError(
                    "GROQ_API_KEY",
                    "groq",
                    "The configured Groq API key was rejected (401).",
                ) from exc
            log.warning("groq health probe failed: %s", type(exc).__name__)
            return False

    def invoke_json(self, system: str, user: str) -> dict[str, Any]:
        """Completion coerced into a JSON object.

        Small models often wrap JSON in prose or code fences, so we try a strict
        parse, then a fenced-block parse, then the first balanced object.
        """
        raw = self.invoke(system, user)
        data = self._parse_json(raw)
        if data is None:
            log.warning("groq returned unparsable JSON (len=%d)", len(raw))
            raise LLMError("The assistant returned an unreadable response. Please retry.")
        return data

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any] | None:
        if not raw:
            return None
        candidates = [raw]
        fenced = _FENCE.search(raw)
        if fenced:
            candidates.append(fenced.group(1))
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            candidates.append(raw[start : end + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    # ---------------- health ----------------

    def is_configured(self) -> bool:
        return self._config.is_configured("groq")


@lru_cache(maxsize=1)
def get_llm() -> ChatGroq:
    """The shared, lazily constructed ChatGroq client."""
    return get_groq_service().llm


@lru_cache(maxsize=1)
def get_groq_service() -> GroqService:
    return GroqService()


def reset_llm_cache() -> None:
    get_groq_service.cache_clear()
    get_llm.cache_clear()