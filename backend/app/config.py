from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    ADMIN_EMAIL: str = "admin@shoply.dev"
    ADMIN_PASSWORD: str = ""

    # --- Milestone 2: AI / RAG (optional; empty defaults keep the app bootable) ---
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_TEMPERATURE: float = 0.2
    GROQ_MAX_TOKENS: int = 800

    HF_API_KEY: str = ""
    HF_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    HF_API_URL: str = "https://router.huggingface.co/hf-inference"
    HF_EMBED_BATCH_SIZE: int = 16

    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "ecommerce_knowledge"

    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 120
    RAG_TOP_K: int = 5
    RAG_MIN_SCORE: float = 0.30
    RAG_DOCUMENTS_DIR: str = "documents"
    RAG_MAX_UPLOAD_MB: int = 10

    ROUTER_CONFIDENCE_THRESHOLD: float = 0.80
    CHAT_MAX_MESSAGE_LENGTH: int = 1000


settings = Settings()
