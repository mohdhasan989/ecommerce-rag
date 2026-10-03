"""Chatbot API.

    POST /api/chat          -> end-to-end RAG / product / order answer
    POST /api/chat/feedback -> one 1-3 experience rating per conversation
    GET  /api/chat/health   -> redacted connectivity/configuration report

Mounted under the existing ``/api`` prefix like every other router in the
project, and reuses the existing JWT dependency for order questions.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.config import get_ai_config
from app.ai.context_builder import build_context, generate_answer
from app.ai.exceptions import AIError, ConfigurationError
from app.ai.handlers import order_handler, product_handler
from app.ai.llm.groq_client import get_groq_service
from app.ai.rag.retriever import retrieve
from app.ai.router.intent_router import Intent, get_router
from app.database import get_db
from app.dependencies.auth import get_current_user_optional
from app.services import feedback_service

log = logging.getLogger("app.chat")

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------- schemas


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, description="The customer's question.")


class RetrievedChunkOut(BaseModel):
    text: str
    score: float | None = None
    metadata: dict = Field(default_factory=dict)


class ChatOut(BaseModel):
    answer: str
    intent: str
    confidence: float
    route: str
    sources: list[str] = Field(default_factory=list)
    requires_auth: bool = False
    debug: dict[str, Any] = Field(default_factory=dict)


class ChatHealthOut(BaseModel):
    status: str
    groq: str
    qdrant: str
    embeddings: str
    model: str
    embedding_model: str
    collection: str
    router_confidence_threshold: float
    top_k: int
    chunk_size: int
    chunk_overlap: int
    rag: str
    chat: str = "unavailable"
    notes: list[str] = Field(default_factory=list)


class ChatFeedbackIn(BaseModel):
    """One experience rating for a finished conversation.

    Deliberately has no ``user_id``: the chatbot is public, and ownership is
    derived from the caller's JWT so a client can never rate on someone
    else's behalf.
    """

    conversation_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Id shared by every message of the finished conversation.",
    )
    rating: int = Field(..., ge=1, le=3, description="1 = Bad, 2 = Neutral, 3 = Excellent.")


class ChatFeedbackOut(BaseModel):
    success: bool = True


# ---------------------------------------------------------------- endpoints


@router.post("", response_model=ChatOut)
def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
) -> ChatOut:
    """Answer a customer question.

    Pipeline: router -> confidence gate -> route (RAG | product | order)
              -> context builder -> Groq -> answer.
    """
    config = get_ai_config()
    message = (payload.message or "").strip()

    # --- empty / oversized input -------------------------------------
    if not message:
        raise HTTPException(400, "Please enter a message.")
    if len(message) > config.max_message_length:
        raise HTTPException(
            400,
            f"Your message is too long. Please keep it under {config.max_message_length} characters.",
        )

    started = time.perf_counter()

    # --- capability gate: Groq powers the router and the final answer for
    # --- every intent, so it is the only hard requirement up front.
    if not config.is_configured("groq"):
        raise ConfigurationError(config.missing("groq"), "groq")

    # --- 1. intent ---------------------------------------------------
    decision = get_router().classify(message)

    # --- 2. confidence gate: low confidence never reaches RAG/DB -----
    if decision.needs_clarification:
        clarification = get_router().clarification(message, decision)
        return ChatOut(
            answer=clarification,
            intent=decision.intent,
            confidence=decision.confidence,
            route=decision.route,
            debug={
                "reason": decision.reason,
                "threshold": decision.threshold,
                "retrieval": {"called": False, "reason": "low confidence"},
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )

    # --- 3. route ----------------------------------------------------
    retrieval = None
    route_context = None
    if decision.intent == Intent.RAG:
        # Only the RAG route needs embeddings + Qdrant; product/order stay
        # available on Groq + MySQL alone.
        if not config.is_configured("rag"):
            raise ConfigurationError(config.missing("rag"), "rag")
        retrieval = retrieve(message, top_k=config.top_k)
        if retrieval.is_empty:
            answer = (
                "I could not find that in our store documents just now. "
                "Please contact our support team and we'll answer you directly."
            )
            return ChatOut(
                answer=answer,
                intent=decision.intent,
                confidence=decision.confidence,
                route=decision.route,
                debug={
                    "reason": decision.reason,
                    "retrieval": retrieval.as_dict(),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
    elif decision.intent == Intent.PRODUCT:
        route_context = product_handler(db, message)
    elif decision.intent == Intent.ORDER:
        route_context = order_handler(db, user, message)
    else:
        clarification = get_router().clarification(message, decision)
        return ChatOut(
            answer=clarification,
            intent=decision.intent,
            confidence=decision.confidence,
            route="clarification",
            debug={
                "reason": decision.reason or "unknown intent",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )

    # --- 4. context builder + 5. final grounded answer ----------------
    answer_context = build_context(
        decision=decision, retrieval=retrieval, route_context=route_context
    )
    answer = generate_answer(message, answer_context)

    debug: dict[str, Any] = {
        "reason": decision.reason,
        "threshold": decision.threshold,
        "context": answer_context.as_dict(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    if retrieval is not None:
        debug["retrieval"] = {
            "called": True,
            "top_k": retrieval.top_k,
            "count": len(retrieval.chunks),
            "chunks": [
                RetrievedChunkOut(**chunk.as_dict()).model_dump() for chunk in retrieval.chunks
            ],
        }
    if route_context is not None:
        debug["route_result"] = route_context.as_dict()
        debug["records"] = route_context.data

    return ChatOut(
        answer=answer,
        intent=decision.intent,
        confidence=decision.confidence,
        route=decision.route,
        sources=answer_context.sources,
        requires_auth=bool(route_context and route_context.extra.get("requires_auth")),
        debug=debug,
    )


@router.post("/feedback", response_model=ChatFeedbackOut)
def chat_feedback(
    payload: ChatFeedbackIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
) -> ChatFeedbackOut:
    """Record one 1-3 experience rating for a finished chatbot conversation.

    Public endpoint: anonymous visitors may rate a conversation, while a signed
    in customer has the rating attributed to their account. An invalid token is
    ignored rather than rejected so a stale session can never lose feedback.
    """
    feedback_service.create_feedback(
        db,
        conversation_id=payload.conversation_id,
        rating=payload.rating,
        user=user,
    )
    return ChatFeedbackOut(success=True)


@router.get("/health", response_model=ChatHealthOut)
def chat_health() -> ChatHealthOut:
    """Development health check. Reports configuration only - never secrets."""
    config = get_ai_config()
    notes: list[str] = []

    groq_state = config.status()["groq"]
    embeddings_state = config.status()["embeddings"]
    groq_ready = config.is_configured("groq")

    # Real connectivity probes, tolerant of missing keys.
    if groq_ready:
        try:
            groq_state = "reachable" if get_groq_service().ping() else "unreachable"
        except ConfigurationError:
            groq_state = "invalid_api_key"
            groq_ready = False
            notes.append("GROQ_API_KEY was rejected by the Groq API (401).")
        except Exception:  # noqa: BLE001
            groq_state = "unreachable"
            groq_ready = False
    else:
        notes.append("Groq is not configured; set GROQ_API_KEY.")

    qdrant_state = config.status()["qdrant"]
    if config.is_configured("qdrant"):
        try:
            from app.ai.vectorstore.qdrant_client import get_vector_store

            qdrant_state = "connected" if get_vector_store().ping() else "unreachable"
        except AIError:
            qdrant_state = "unreachable"
        except Exception:  # noqa: BLE001
            qdrant_state = "unreachable"
    else:
        notes.append("Qdrant is not configured; set QDRANT_URL and QDRANT_API_KEY.")

    if config.is_configured("embeddings"):
        try:
            from app.ai.embeddings.hf_embeddings import get_embeddings

            size = get_embeddings().dimension()
            embeddings_state = f"configured (dim={size})"
        except AIError:
            embeddings_state = "configured but unreachable"
            notes.append("Embedding provider did not respond.")
    else:
        notes.append("Embeddings are not configured; set HF_API_KEY.")

    missing = config.missing("rag")
    rag_ready = not missing
    if missing:
        notes.append("RAG is disabled until all of: " + ", ".join(missing) + " are set.")

    if not groq_ready:
        notes.append("Chat is disabled until GROQ_API_KEY is set and valid.")

    return ChatHealthOut(
        status="ok" if (rag_ready and groq_ready) else "degraded",
        groq=groq_state,
        qdrant=qdrant_state,
        embeddings=embeddings_state,
        model=config.groq_model,
        embedding_model=config.hf_embedding_model,
        collection=config.qdrant_collection,
        router_confidence_threshold=config.router_confidence_threshold,
        top_k=config.top_k,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        rag="ready" if rag_ready else "unavailable",
        chat="ready" if groq_ready else "unavailable",
        notes=notes,
    )


__all__ = ["router", "ChatIn", "ChatOut", "ChatHealthOut", "ChatFeedbackIn", "ChatFeedbackOut"]