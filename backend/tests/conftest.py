import os
os.environ.update(DATABASE_URL="sqlite://", JWT_SECRET_KEY="test-secret-key-for-pytests-only-0123456789",
                  ADMIN_EMAIL="admin@test.com", ADMIN_PASSWORD="AdminPass123!")
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import seed as seed_mod
from app.database import Base, get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed_mod.SessionLocal = TestSession
    seed_mod.seed()

    def _db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def user_h(client):
    return login(client, "alice@demo.com", "Password123!")


@pytest.fixture()
def user2_h(client):
    return login(client, "bob@demo.com", "Password123!")


@pytest.fixture()
def admin_h(client):
    return login(client, "admin@test.com", "AdminPass123!")
