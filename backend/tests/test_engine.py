from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.assistant import answer
from app.models import Alert, Asset
from app.services import (build_dashboard, detect_anomalies, ensure_readings, forecast_tomorrow, inject_fault, seed_demo,
                          telemetry)
from app.solar import IST, floor_ist_hour

NOON = datetime(2026, 10, 20, 12, 30, tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)
NIGHT = datetime(2026, 10, 20, 2, 30, tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)


def _seed(db, now=NOON):
    seed_demo(db, now, with_users=False)


def test_readings_follow_india_daylight(db):
    _seed(db)
    t = telemetry(db, 24, now=NOON)
    peak = max(t, key=lambda p: p["power_kw"])
    assert (peak["timestamp"].astimezone(IST)).hour == 12
    assert all(p["power_kw"] == 0 for p in t if p["timestamp"].astimezone(IST).hour in (0, 3, 22))


def test_catch_up_is_idempotent(db):
    _seed(db)
    assert ensure_readings(db, NOON) == 0
    assert ensure_readings(db, NOON + timedelta(hours=2)) == 3 * 2  # 3 assets x 2 new hours


def test_dashboard_numbers_agree(db):
    _seed(db)
    d = build_dashboard(db, NOON)
    s = d["summary"]
    assert s["current_power_kw"] == round(sum(a["power_kw"] for a in d["assets"]), 1)
    assert 0 < s["current_power_kw"] <= sum(a["capacity_kw"] for a in d["assets"])
    assert 0 < s["performance_percent"] <= 100 and s["energy_today_kwh"] > 0
    assert d["generation"][-1]["actual_kwh"] is None  # future hours have no actual value yet
    assert all(0 <= a["power_kw"] <= a["capacity_kw"] for a in d["assets"])


def test_night_dashboard_is_safe(db):
    _seed(db, NIGHT)
    d = build_dashboard(db, NIGHT)
    assert d["summary"]["current_power_kw"] == 0
    assert d["summary"]["change_percent"] == 0 or isinstance(d["summary"]["change_percent"], float)


def test_seeded_fault_is_found_and_marks_asset_for_review(db):
    _seed(db)
    alerts = db.scalars(select(Alert)).all()
    assert len(alerts) == 1 and alerts[0].asset_id == "SOL-003" and alerts[0].kind == "underperformance"
    assert "kWh" in alerts[0].description
    status = {a["id"]: a["status"] for a in build_dashboard(db, NOON)["assets"]}
    assert status == {"SOL-001": "online", "SOL-002": "online", "SOL-003": "review"}


def test_healthy_assets_raise_no_alerts(db):
    _seed(db)
    assert {a.asset_id for a in db.scalars(select(Alert)).all()} == {"SOL-003"}


def test_outage_detection_is_critical_and_marks_offline(db):
    _seed(db)
    assert inject_fault(db, "SOL-001", 0.0, hours=4, upto=floor_ist_hour(NOON)) == 4
    detect_anomalies(db, NOON)
    outage = db.scalar(select(Alert).where(Alert.asset_id == "SOL-001"))
    assert outage.kind == "outage" and outage.severity == "critical"
    assert {a["id"]: a["status"] for a in build_dashboard(db, NOON)["assets"]}["SOL-001"] == "offline"
    assert build_dashboard(db, NOON)["summary"]["active_assets"] == 2


def test_detection_is_idempotent(db):
    _seed(db)
    before = db.scalar(select(func.count()).select_from(Alert))
    for _ in range(3):
        detect_anomalies(db, NOON)
    assert db.scalar(select(func.count()).select_from(Alert)) == before


def test_two_bad_hours_do_not_trigger_underperformance(db):
    _seed(db)
    inject_fault(db, "SOL-002", 0.4, hours=2, upto=floor_ist_hour(NOON))  # fewer than the 3-hour rule
    detect_anomalies(db, NOON)
    assert db.scalar(select(func.count()).select_from(Alert).where(Alert.asset_id == "SOL-002")) == 0


def test_acknowledged_alert_returns_asset_to_online(db):
    _seed(db)
    al = db.scalar(select(Alert))
    from app.models import now_utc
    al.acknowledged_at, al.acknowledged_by = now_utc(), "admin"
    db.commit()
    assert {a["id"]: a["status"] for a in build_dashboard(db, NOON)["assets"]}["SOL-003"] == "online"


def test_forecast_shape(db):
    _seed(db)
    f = forecast_tomorrow(db, NOON)
    assert len(f["points"]) == 15 and f["basis_days"] >= 6 and f["total_kwh"] > 100
    assert f["peak_time"] in {"11:00", "12:00", "13:00"}


def test_assistant_is_grounded_and_cites_numbers(db):
    _seed(db)
    for question, intent in [("How much energy today?", "energy"), ("Why is SOL-003 low?", "asset"), ("any alerts?", "alerts"),
                             ("tomorrow forecast", "forecast"), ("co2 avoided", "co2"), ("which asset is best", "rank"),
                             ("current power", "power"), ("hello", "help")]:
        r = answer(db, question, NOON)
        assert r["intent"] == intent, question
        assert r["answer"] and (r["sources"] or intent == "help")


def test_assistant_refuses_to_guess(db):
    _seed(db)
    r = answer(db, "who will win the cricket match", NOON)
    assert r["intent"] == "unknown" and "won't guess" in r["answer"]
    fault = answer(db, "what is wrong with SOL-003", NOON)["answer"]
    assert "cannot show the cause" in fault  # never invents a root cause


def test_simulation_is_disabled_in_production(db, monkeypatch):
    import dataclasses
    from app import services
    from app.models import Asset, Reading
    monkeypatch.setattr(services, "settings", dataclasses.replace(services.settings, simulate_readings=False))
    db.add(Asset(id="REAL-1", name="Real Plant", location="Somewhere", capacity_kw=10, performance_factor=0.9))
    db.commit()
    assert ensure_readings(db, NOON) == 0
    assert db.scalar(select(func.count()).select_from(Reading)) == 0  # no invented data for real assets
    d = build_dashboard(db, NOON)
    assert d["summary"]["current_power_kw"] == 0 and d["alerts"] == []


def test_bootstrap_admin_only_when_none_exists(db):
    from app.models import User
    from app.services import bootstrap_admin
    assert bootstrap_admin(db, "Boss@Example.com", "a-long-password") is True
    assert db.scalar(select(User)).email == "boss@example.com"
    assert bootstrap_admin(db, "other@example.com", "another-long-pass") is False
    assert bootstrap_admin(db, "", "") is False


def test_assets_carry_sparklines(db):
    _seed(db)
    for a in build_dashboard(db, NOON)["assets"]:
        assert len(a["spark"]) == 24 and all(v >= 0 for v in a["spark"])


def test_ratio_series_exposes_the_seeded_fault(db):
    from app.services import ratio_series
    _seed(db)
    r = ratio_series(db, "SOL-003", 72, NOON)
    assert r["threshold_percent"] == 75.0 and r["points"]
    low = [p for p in r["points"] if p["ratio_percent"] < 75]
    assert len(low) >= 3 and all(p["ratio_percent"] > 90 for p in ratio_series(db, "SOL-001", 72, NOON)["points"])
    assert ratio_series(db, "NOPE", 72, NOON) is None


def test_heatmap_shape(db):
    from app.services import heatmap
    _seed(db)
    h = heatmap(db, 7, NOON)
    assert len(h["days"]) == 7 and all(len(r["values"]) == 24 for r in h["days"])
    assert h["max_kw"] > 20 and h["days"][0]["values"][2] == 0 and h["days"][-1]["values"][20] is None  # night = 0, future = None


def test_fault_injection_is_idempotent(db):
    from app.models import Reading
    _seed(db)
    def powers():
        return [r.power_kw for r in db.scalars(select(Reading).where(Reading.asset_id == "SOL-001").order_by(Reading.ts.desc()).limit(6))]
    inject_fault(db, "SOL-001", 0.45, hours=4, upto=floor_ist_hour(NOON))
    once = powers()
    for _ in range(3):
        inject_fault(db, "SOL-001", 0.45, hours=4, upto=floor_ist_hour(NOON))
    assert powers() == once  # repeated clicks must not drive the asset to zero


def test_data_after_the_clock_is_ignored(db):
    """With a pinned demo clock earlier than stored data, future rows must not leak into today's numbers."""
    from app.services import build_dashboard
    _seed(db, NIGHT + timedelta(hours=18))          # data generated up to ~20:30 IST
    at_noon = build_dashboard(db, NOON)
    assert at_noon["summary"]["energy_today_kwh"] < 450          # a full sunny day is ~600+ kWh
    assert at_noon["generation"][-1]["actual_kwh"] is None       # 19:00 has not happened at noon


def test_demo_clock_setting_validation():
    import pytest
    from app.config import Settings
    Settings(demo_clock="12:30").validate()
    for bad in ("25:00", "noon", "12:60"):
        with pytest.raises(RuntimeError):
            Settings(demo_clock=bad).validate()
    with pytest.raises(RuntimeError):
        Settings(app_env="production", jwt_secret="x" * 40, demo_clock="12:30").validate()


def test_now_utc_honours_demo_clock():
    from app import models
    from app.solar import to_ist
    models.set_demo_clock("12:30")
    try:
        local = to_ist(models.now_utc())
        assert (local.hour, local.minute) == (12, 30)
    finally:
        models.set_demo_clock(None)
