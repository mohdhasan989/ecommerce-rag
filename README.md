# Shoply — Milestone 1 (React + FastAPI + MySQL)

No Docker, no RAG/LLM. Run directly on your machine. Needs Python 3.11+, Node 18+, MySQL 8.

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
pytest                   # 15 tests (in-memory SQLite)
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

## Notes
- Product rating is a placeholder derived from the product id (no rating column in the schema).
- Deleting a product in admin deactivates it, so order history stays intact.