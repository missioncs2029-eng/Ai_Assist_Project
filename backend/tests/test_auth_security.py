from app.config import DEFAULT_SECRET, Settings
from app.security import hash_password, verify_password
from conftest import ADMIN, VIEWER


def test_health_and_security_headers(client):
    r = client.get("/health")
    assert r.json()["status"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/auth/demo-accounts").headers["cache-control"] == "no-store"


def test_login_success_and_me(client):
    r = client.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["email"] == ADMIN["email"]


def test_login_is_case_insensitive_and_rejects_bad_password(client):
    assert client.post("/api/auth/login", json={"email": ADMIN["email"].upper(), "password": ADMIN["password"]}).status_code == 200
    assert client.post("/api/auth/login", json={**ADMIN, "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@x.io", "password": "whatever1"}).status_code == 401


def test_swagger_oauth_token_endpoint(client):
    r = client.post("/api/auth/token", data={"username": VIEWER["email"], "password": VIEWER["password"]})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


def test_protected_routes_need_a_valid_token(client):
    for path in ["/api/dashboard", "/api/assets", "/api/alerts", "/api/forecast", "/api/system"]:
        assert client.get(path).status_code == 401
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer not.a.token"}).status_code == 401


def test_login_rate_limit(client):
    codes = [client.post("/api/auth/login", json={**ADMIN, "password": "bad"}).status_code for _ in range(10)]
    assert codes[:8] == [401] * 8 and codes[8] == 429


def test_successful_logins_are_never_rate_limited(client):
    for _ in range(15):  # e.g. rehearsing a demo: sign in / out many times
        assert client.post("/api/auth/login", json=ADMIN).status_code == 200


def test_success_resets_the_failure_counter(client):
    for _ in range(5):
        client.post("/api/auth/login", json={**ADMIN, "password": "bad"})
    assert client.post("/api/auth/login", json=ADMIN).status_code == 200
    assert all(client.post("/api/auth/login", json={**ADMIN, "password": "bad"}).status_code == 401 for _ in range(7))


def test_register_flow(client):
    body = {"name": "New Person", "email": "new.person@example.com", "password": "LongEnough1"}
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201 and r.json()["user"]["role"] == "viewer"
    assert client.post("/api/auth/register", json=body).status_code == 409
    assert client.post("/api/auth/register", json={**body, "email": "x@y.io", "password": "short"}).status_code == 422
    assert client.post("/api/auth/register", json={**body, "email": "not-an-email"}).status_code == 422


def test_viewer_cannot_use_admin_endpoints(client, viewer):
    asset = {"name": "Test", "location": "Somewhere", "capacity_kw": 5}
    assert client.get("/api/dashboard", headers=viewer).status_code == 200
    assert client.post("/api/assets", json=asset, headers=viewer).status_code == 403
    assert client.post("/api/alerts/1/ack", headers=viewer).status_code == 403
    assert client.post("/api/readings", json={"readings": []}, headers=viewer).status_code in (403, 422)
    assert client.post("/api/demo/reset", headers=viewer).status_code == 403
    assert client.get("/api/audit", headers=viewer).status_code == 403


def test_password_hashing():
    a, b = hash_password("Secret123"), hash_password("Secret123")
    assert a != b and a.startswith("scrypt$")
    assert verify_password("Secret123", a) and not verify_password("secret123", a)
    assert not verify_password("x", "garbage")


def test_production_refuses_default_secret():
    import pytest
    with pytest.raises(RuntimeError):
        Settings(app_env="production", jwt_secret=DEFAULT_SECRET).validate()
    with pytest.raises(RuntimeError):
        Settings(app_env="production", jwt_secret="short").validate()
    with pytest.raises(RuntimeError):
        Settings(app_env="production", jwt_secret="x" * 40, admin_password="short").validate()
    Settings(app_env="production", jwt_secret="x" * 40).validate()


def test_audit_trail_records_logins(client, admin):
    actions = [a["action"] for a in client.get("/api/audit", headers=admin).json()]
    assert "login" in actions
