import os

# Must be set BEFORE the app is imported: tests use a throw-away in-memory database.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "development"
os.environ["SEED_DEMO"] = "true"
os.environ["ALLOW_REGISTRATION"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, make_engine
from app.main import app
from app.security import login_limiter
from sqlalchemy.orm import sessionmaker

ADMIN = {"email": "admin@solarpulse.demo", "password": "Admin@12345"}
VIEWER = {"email": "viewer@solarpulse.demo", "password": "Viewer@12345"}


@pytest.fixture(autouse=True)
def _reset_limiter():
    login_limiter.reset()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _headers(client, creds):
    r = client.post("/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def admin(client):
    h = _headers(client, ADMIN)
    client.post("/api/demo/reset", headers=h)  # pristine demo data for every test
    return h


@pytest.fixture()
def viewer(client):
    return _headers(client, VIEWER)


@pytest.fixture()
def db():
    """Isolated database session for service-level tests with a fixed clock."""
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as session:
        yield session
