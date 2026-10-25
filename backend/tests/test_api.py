from datetime import datetime, timedelta, timezone

from app.solar import floor_ist_hour


def test_dashboard_shape_and_consistency(client, admin):
    d = client.get("/api/dashboard", headers=admin).json()
    assert {"summary", "generation", "power", "assets", "alerts"} <= d.keys()
    assert d["summary"]["current_power_kw"] == round(sum(a["power_kw"] for a in d["assets"]), 1)
    assert len(d["assets"]) == 3 and d["timezone"] == "Asia/Kolkata"


def test_telemetry_limits_and_filter(client, admin):
    assert len(client.get("/api/telemetry?hours=48", headers=admin).json()) == 48
    one = client.get("/api/telemetry?hours=24&asset_id=SOL-001", headers=admin).json()
    allx = client.get("/api/telemetry?hours=24", headers=admin).json()
    assert len(one) == 24 and sum(p["power_kw"] for p in one) <= sum(p["power_kw"] for p in allx)
    for bad in ("0", "169", "abc"):
        assert client.get(f"/api/telemetry?hours={bad}", headers=admin).status_code == 422


def test_csv_export(client, admin):
    r = client.get("/api/export/readings.csv?hours=6", headers=admin)
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0] == "timestamp_utc,asset_id,power_kw,irradiance_wm2,temperature_c" and len(lines) == 1 + 6 * 3


def test_asset_crud(client, admin):
    r = client.post("/api/assets", json={"name": "Parking Canopy", "location": "Pune, IN", "capacity_kw": 12.5}, headers=admin)
    assert r.status_code == 201
    aid = r.json()["id"]
    assert aid.startswith("SOL-") and r.json()["capacity_kw"] == 12.5
    assert client.post("/api/assets", json={"id": aid, "name": "Dup", "location": "Nowhere", "capacity_kw": 1}, headers=admin).status_code == 409
    p = client.patch(f"/api/assets/{aid}", json={"name": "Canopy B"}, headers=admin)
    assert p.status_code == 200 and p.json()["name"] == "Canopy B"
    assert len(client.get("/api/assets", headers=admin).json()) == 4
    assert client.delete(f"/api/assets/{aid}", headers=admin).status_code == 204
    assert client.delete(f"/api/assets/{aid}", headers=admin).status_code == 404
    assert len(client.get("/api/assets", headers=admin).json()) == 3


def test_asset_validation(client, admin):
    bad = [{"name": "x", "location": "Valid place", "capacity_kw": 5}, {"name": "Valid", "location": "Valid place", "capacity_kw": 0},
           {"name": "Valid", "location": "Valid place", "capacity_kw": 5, "performance_factor": 1.5},
           {"id": "bad id!", "name": "Valid", "location": "Valid place", "capacity_kw": 5}]
    for body in bad:
        assert client.post("/api/assets", json=body, headers=admin).status_code == 422, body


def test_alert_ack_unack_flow(client, admin):
    alerts = client.get("/api/alerts", headers=admin).json()
    assert alerts and alerts[0]["acknowledged"] is False
    aid = alerts[0]["id"]
    ack = client.post(f"/api/alerts/{aid}/ack", headers=admin).json()
    assert ack["acknowledged"] and ack["acknowledged_by"] == "admin@solarpulse.demo"
    assert client.get("/api/alerts?open_only=true", headers=admin).json() == []
    assert client.post(f"/api/alerts/{aid}/unack", headers=admin).json()["acknowledged"] is False
    assert client.post("/api/alerts/99999/ack", headers=admin).status_code == 404


def test_ingest_inserts_updates_and_validates(client, admin):
    ts = floor_ist_hour(datetime.now(timezone.utc).replace(tzinfo=None)) - timedelta(hours=5)
    row = {"asset_id": "SOL-001", "ts": ts.replace(tzinfo=timezone.utc).isoformat(), "power_kw": 3.3}
    r = client.post("/api/readings", json={"readings": [row]}, headers=admin)
    assert r.status_code == 201 and r.json()["updated"] == 1 and r.json()["inserted"] == 0  # hour already exists -> upsert
    assert client.post("/api/readings", json={"readings": [{**row, "asset_id": "NOPE"}]}, headers=admin).status_code == 422
    assert client.post("/api/readings", json={"readings": [{**row, "power_kw": 9999}]}, headers=admin).status_code == 422
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert client.post("/api/readings", json={"readings": [{**row, "ts": future}]}, headers=admin).status_code == 422
    assert client.post("/api/readings", json={"readings": [{**row, "power_kw": -1}]}, headers=admin).status_code == 422
    assert client.post("/api/readings", json={"readings": []}, headers=admin).status_code == 422
    assert client.post("/api/readings", json={"readings": [row] * 501}, headers=admin).status_code == 422


def test_assistant_endpoint(client, viewer):
    r = client.post("/api/assistant", json={"question": "how much energy today?"}, headers=viewer)
    assert r.status_code == 200 and r.json()["intent"] == "energy" and r.json()["sources"]
    assert client.post("/api/assistant", json={"question": "x"}, headers=viewer).status_code == 422
    assert client.post("/api/assistant", json={"question": "a" * 501}, headers=viewer).status_code == 422


def test_demo_fault_then_reset(client, admin):
    r = client.post("/api/demo/fault", json={"asset_id": "SOL-001", "ratio": 0.0, "hours": 4}, headers=admin)
    assert r.status_code == 200 and r.json()["hours_modified"] == 4
    alerts = client.get("/api/alerts", headers=admin).json()
    assert any(a["asset_id"] == "SOL-001" and a["kind"] == "outage" for a in alerts)
    assert client.post("/api/demo/fault", json={"asset_id": "NOPE"}, headers=admin).status_code == 404
    assert client.post("/api/demo/fault", json={"asset_id": "SOL-001", "ratio": 5}, headers=admin).status_code == 422
    client.post("/api/demo/reset", headers=admin)
    assert all(a["asset_id"] != "SOL-001" for a in client.get("/api/alerts", headers=admin).json())


def test_system_info(client, admin):
    s = client.get("/api/system", headers=admin).json()
    assert s["database"] == "sqlite" and s["assets"] == 3 and s["readings"] >= 3 * 24 * 6 and s["users"] >= 2


def test_cors(client):
    assert client.get("/health", headers={"Origin": "http://localhost:3001"}).headers.get("access-control-allow-origin") == "http://localhost:3001"
    assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": "http://evil.example"}).headers


def test_analytics_endpoints(client, viewer):
    r = client.get("/api/analytics/ratio?asset_id=SOL-003&hours=72", headers=viewer)
    assert r.status_code == 200 and r.json()["points"] and r.json()["min_hours"] == 3
    assert client.get("/api/analytics/ratio?asset_id=NOPE", headers=viewer).status_code == 404
    assert client.get("/api/analytics/ratio?asset_id=SOL-003&hours=5", headers=viewer).status_code == 422
    h = client.get("/api/analytics/heatmap?days=5", headers=viewer).json()
    assert len(h["days"]) == 5 and client.get("/api/analytics/heatmap?days=99", headers=viewer).status_code == 422
    assert client.get("/api/analytics/heatmap").status_code == 401


def test_demo_clock_endpoint(client, admin, viewer):
    from app import models
    try:
        assert client.post("/api/demo/clock", json={"time": "12:30"}, headers=viewer).status_code == 403
        assert client.post("/api/demo/clock", json={"time": "25:99"}, headers=admin).status_code == 422
        assert client.post("/api/demo/clock", json={"time": "12:30"}, headers=admin).status_code == 200
        d = client.get("/api/dashboard", headers=admin).json()
        assert d["demo_clock"] == "12:30" and d["demo_mode"] is True and d["summary"]["current_power_kw"] > 5
        assert client.post("/api/demo/clock", json={"time": None}, headers=admin).status_code == 200
        assert client.get("/api/dashboard", headers=admin).json()["demo_clock"] is None
    finally:
        models.set_demo_clock(None)
