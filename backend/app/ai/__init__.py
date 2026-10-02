"""Milestone 2 AI/RAG layer.

Sub-packages:
    config      centralised AI configuration (derived from app.config.Settings)
    llm         reusable Groq chat model service
    embeddings  Hugging Face embedding service (documents + queries)
    vectorstore Qdrant Cloud vector store service
    rag         document loading, chunking, ingestion, retrieval
    router      LLM intent router with confidence gating

Public surface is intentionally small so the API router stays thin.
"""
from app.ai.config import AIConfig, ai_config, get_ai_config
from app.ai.context_builder import build_context, generate_answer
from app.ai.exceptions import (
    AIError,
    ConfigurationError,
    DocumentLoadError,
    EmbeddingError,
    LLMError,
    VectorStoreError,
)
from app.ai.handlers import order_handler, product_handler
from app.ai.rag.retriever import retrieve
from app.ai.router.intent_router import Intent, RouteDecision, get_router

__all__ = [
    "AIConfig",
    "ai_config",
    "get_ai_config",
    "AIError",
    "ConfigurationError",
    "EmbeddingError",
    "LLMError",
    "VectorStoreError",
    "DocumentLoadError",
    "Intent",
    "RouteDecision",
    "get_router",
    "retrieve",
    "build_context",
    "generate_answer",
    "product_handler",
    "order_handler",
]