# Backend (FastAPI + SQLAlchemy + Alembic + MySQL)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # edit DATABASE_URL, JWT_SECRET_KEY, ADMIN_PASSWORD
mysql -u root -p -e "CREATE DATABASE ecommerce_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
alembic upgrade head                                # create tables
python -m app.seed                                  # demo data + admin (safe to re-run)
uvicorn app.main:app --reload                       # http://localhost:8000/docs
pytest                                              # tests use in-memory SQLite
```
Demo logins: alice@demo.com / bob@demo.com (Password123!), admin from `.env`.
