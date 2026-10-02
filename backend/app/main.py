from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import admin, auth, cart, chatbot, orders
from app.routers.catalog import categories, products
from app.utils.errors import register_handlers

app = FastAPI(title="E-commerce API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
register_handlers(app)

for r in (auth.router, products, categories, cart.router, orders.router, admin.router, chatbot.router):
    app.include_router(r, prefix="/api")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}