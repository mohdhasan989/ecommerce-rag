# Shoply — (React + FastAPI + MySQL + modular RAG chatbot)

 Run directly on your machine. Needs Python 3.11+, Node 18+, MySQL 8.

## 1. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # set DATABASE_URL password, JWT_SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
mysql -u root -p -e "CREATE DATABASE ecommerce_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
alembic upgrade head     # create tables
python -m app.seed       # demo data + admin (safe to re-run)
uvicorn app.main:app --reload      # API docs: http://localhost:8000/docs
pytest                   # 74 tests (in-memory SQLite, all providers mocked)
```
ADMIN_EMAIL must be a normal domain (e.g. admin@shoply.dev) — `.local`/`.test` are rejected by email validation.

## 2. Frontend
```bash
cd frontend
cp .env.example .env     # VITE_API_URL=http://localhost:8000
npm install
npm run dev              # http://localhost:5173
```
Optional API check against a running, seeded backend (safe to re-run — it is
re-runnable against a persistent database):
```bash
cd frontend
npm i --no-save vite-node
ADMIN_EMAIL=<admin email> ADMIN_PASSWORD=<admin password> VITE_API_URL=http://localhost:8000 npx vite-node tests/api-integration.mjs
```

## Opening the dev server from a phone / another machine
The Vite server binds to all interfaces, so any address on your LAN works — but
the backend must allow that origin too. Add it to `backend/.env`:
```
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://<your-lan-ip>:5173
```
and point HMR at the same address in `frontend/.env`:
```
VITE_HMR_HOST=<your-lan-ip>
```

## Logins
- Users: alice@demo.com, bob@demo.com — `Password123!`
- Admin: the ADMIN_EMAIL / ADMIN_PASSWORD from backend/.env (opens /admin after login)

## 3. AI chatbot (Milestone 2)

Three providers, all cloud-hosted. The app **boots and serves Milestone 1
normally with none of these set** — only `/api/chat` and the RAG route refuse to
work until they are configured.

| Capability | Provider | Variable |
| --- | --- | --- |
| Intent routing + answer writing | Groq `llama-3.1-8b-instant` | `GROQ_API_KEY` |
| Embeddings (documents + queries) | Hugging Face `BAAI/bge-small-en-v1.5` | `HF_API_KEY` |
| Vector storage + similarity search | Qdrant Cloud | `QDRANT_URL`, `QDRANT_API_KEY` |

Copy the Milestone 2 block from `backend/.env.example` into `backend/.env` and
fill in real values. Then check what the process can actually reach:

```bash
curl http://localhost:8000/api/chat/health
```

`status` is `ok` only when everything is wired; `degraded` lists exactly what is
missing. The response never contains key material.

### Ingesting documents

Drop `.pdf`, `.txt` or `.md` files in `backend/documents/`, then:

```bash
cd backend
python -m app.ai.rag                              # whole documents/ folder
python -m app.ai.rag --path docs/policy.pdf       # or specific files
python -m app.ai.rag --no-replace                # keep existing chunks
```

Loading → chunking (`800` chars, `120` overlap) → embedding → Qdrant upsert.
Chunk IDs are `uuid5(source | page | chunk_index)`, so re-running the command
replaces a file's chunks instead of duplicating them. The vector dimension is
discovered at runtime, never hardcoded — it is created on the first ingestion
with whatever the configured model returns.

### Endpoints

```bash
# public
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"what is your return policy?"}'

# order questions additionally read your own orders when you pass a token
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"where is my order?"}'
```

The response carries `answer`, `intent`, `confidence`, `route`, `sources` and
`requires_auth`, plus a `debug` block with the router reason, retrieval scores
and the records each route returned.

### How a question is routed

```
message → intent router (Groq) → confidence ≥ 0.80?
                                     │ no  → clarifying question, no lookups
                                     └ yes → RAG (Qdrant) / product (MySQL) / order (MySQL, own rows only)
                                                → context builder → Groq → grounded answer
```

- Product and order data are read live from MySQL. Only documents live in Qdrant.
- Order rows are filtered by the authenticated user's id taken from the JWT, never
  from anything the LLM produced.
- If a lookup returns nothing, the answer says so instead of inventing data.
- A missing or rejected API key returns `503 AI_NOT_CONFIGURED` naming the
  variables to set; a transient provider failure degrades to a clarification
  rather than a 500.

### Module layout

```
backend/app/ai/
  config.py            single config surface over app.config.Settings (redacted)
  exceptions.py        error taxonomy -> HTTP status + safe client message
  prompts.py           router / clarification / grounded-answer prompts
  llm/groq_client.py   shared ChatGroq client + JSON coercion
  embeddings/          LangChain Embeddings over the HF Inference API
  vectorstore/         Qdrant Cloud collection + query_points search
  rag/                 loader, chunker, ingestion CLI, retriever
  router/              intent classification and confidence gating
  handlers.py          product and order queries (MySQL)
  context_builder.py   normalises a route into one prompt-ready context block
```

## Notes
- Product rating is a placeholder derived from the product id (no rating column in the schema).
- Deleting a product in admin deactivates it, so order history stays intact.
- Embeddings run through the Hugging Face Inference API rather than local
  Sentence Transformers, so no multi-hundred-megabyte model download is needed.
