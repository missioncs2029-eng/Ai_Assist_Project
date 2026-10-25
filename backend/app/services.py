"""Data engine: readings catch-up, anomaly detection, dashboard, forecast, demo helpers."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Alert, Asset, AuditLog, Reading, User, active_demo_clock, now_utc
from .security import hash_password
from .solar import CLEAR_SKY, clear_sky_kw, expected_kw, floor_ist_hour, simulate, sun_shape, to_ist

HISTORY_DAYS = 7
GRID_KG_CO2_PER_KWH = 0.71  # approximate Indian grid emission factor - an ASSUMPTION shown to users
DEMO_ACCOUNTS = [
    {"email": "admin@solarpulse.demo", "name": "Demo Admin", "role": "admin", "password": "Admin@12345"},
    {"email": "viewer@solarpulse.demo", "name": "Demo Viewer", "role": "viewer", "password": "Viewer@12345"},
]
DEMO_ASSETS = [
    ("SOL-001", "Rooftop Array A", "Hyderabad, IN", 30.0, 0.924),
    ("SOL-002", "Campus Solar Field", "Warangal, IN", 20.0, 0.891),
    ("SOL-003", "Research Lab Array", "Nellore, IN", 5.0, 0.768),
]


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc)


def audit(db: Session, actor: str, action: str, detail: str = "") -> None:
    db.add(AuditLog(actor=actor[:254], action=action[:60], detail=detail[:300]))
    db.commit()


# ------------------------------------------------------------------ readings
def ensure_readings(db: Session, now: datetime | None = None) -> int:
    """Demo mode only: catch every asset up to the latest whole IST hour with simulated readings."""
    if not settings.simulate_readings:
        return 0
    end = floor_ist_hour(now or now_utc())
    added = 0
    for a in db.scalars(select(Asset)).all():
        last = db.scalar(select(func.max(Reading.ts)).where(Reading.asset_id == a.id))
        ts = end - timedelta(days=HISTORY_DAYS) if last is None else last + timedelta(hours=1)
        rows = []
        while ts <= end:
            p, irr, t = simulate(a.capacity_kw, a.performance_factor, ts)
            rows.append(Reading(asset_id=a.id, ts=ts, power_kw=p, irradiance_wm2=irr, temperature_c=t))
            ts += timedelta(hours=1)
        db.add_all(rows)
        added += len(rows)
    db.commit()
    return added


def inject_fault(db: Session, asset_id: str, ratio: float, hours: int = 4, upto: datetime | None = None) -> int:
    """Demo helper: set the asset's most recent `hours` daylight readings (same day) to `ratio` x healthy output.
    Idempotent: repeating it does not compound the reduction."""
    upto = upto or floor_ist_hour(now_utc())
    asset = db.get(Asset, asset_id)
    if not asset:
        return 0
    rows = db.scalars(select(Reading).where(Reading.asset_id == asset_id, Reading.ts <= upto)
                      .order_by(Reading.ts.desc()).limit(24 * 5)).all()
    by_day: dict = defaultdict(list)
    for r in rows:
        local = to_ist(r.ts)
        if sun_shape(local.hour) > 0.2:
            by_day[local.date()].append(r)
    need = min(hours, 3)
    for day in sorted(by_day, reverse=True):
        if len(by_day[day]) >= need:
            chosen = sorted(by_day[day], key=lambda r: r.ts, reverse=True)[:hours]
            for r in chosen:
                r.power_kw = round(simulate(asset.capacity_kw, asset.performance_factor, r.ts)[0] * ratio, 2)
            db.commit()
            return len(chosen)
    return 0


# ------------------------------------------------------------------ anomaly detection
def _runs(rows: list[tuple[datetime, float, float]], bad) -> list[list[tuple[datetime, float, float]]]:
    runs, cur = [], []
    for item in rows:
        if bad(item) and (not cur or item[0] - cur[-1][0] == timedelta(hours=1)):
            cur.append(item)
        else:
            if cur:
                runs.append(cur)
            cur = [item] if bad(item) else []
    if cur:
        runs.append(cur)
    return runs


def detect_anomalies(db: Session, now: datetime | None = None, lookback_h: int = 72) -> int:
    """Raise (or refresh) alerts from stored readings. Rules are explicit and explainable:

    * outage         - >= 2 consecutive daylight hours with ~0 kW while sun is strong        -> critical
    * underperformance - >= 3 consecutive daylight hours below 75% of the asset's expectation -> warning
                         (critical if the average is below 30%)
    """
    end = floor_ist_hour(now or now_utc())
    since = end - timedelta(hours=lookback_h)
    touched = 0
    for a in db.scalars(select(Asset)).all():
        data = db.execute(select(Reading.ts, Reading.power_kw).where(Reading.asset_id == a.id, Reading.ts >= since, Reading.ts <= end)
                          .order_by(Reading.ts)).all()
        rows = []  # (ts, actual, expected) for daylight hours only
        for ts, power in data:
            exp = expected_kw(a.capacity_kw, a.performance_factor, to_ist(ts).hour)
            if sun_shape(to_ist(ts).hour) > 0.2 and exp > 0:
                rows.append((ts, power, exp))
        found = []
        for run in _runs(rows, lambda r: r[1] <= 0.05 and r[2] > 0.25 * a.capacity_kw * a.performance_factor):
            if len(run) >= 2:
                found.append(("outage", "critical", run))
        outage_ts = {r[0] for _, _, run in found for r in run}
        for run in _runs([r for r in rows if r[0] not in outage_ts], lambda r: r[1] < 0.75 * r[2]):
            if len(run) >= 3:
                ratio = sum(r[1] for r in run) / sum(r[2] for r in run)
                found.append(("underperformance", "critical" if ratio < 0.30 else "warning", run))
        for kind, severity, run in found:
            lost = sum(r[2] - r[1] for r in run)
            first, last = to_ist(run[0][0]), to_ist(run[-1][0])
            ratio = sum(r[1] for r in run) / sum(r[2] for r in run) * 100
            window = f"{first:%d %b %H:%M}-{last:%H:%M} IST"
            if kind == "outage":
                title = f"{a.name}: no output in daylight"
                desc = (f"{a.id} produced ~0 kW for {len(run)} consecutive daylight hours ({window}) while about "
                        f"{run[0][2]:.1f} kW was expected. Estimated lost energy: {lost:.1f} kWh. "
                        "Readings cannot show the cause - check the inverter, breaker and communications.")
            else:
                title = f"{a.name}: output below expectation"
                desc = (f"{a.id} delivered {ratio:.0f}% of its expected output for {len(run)} consecutive daylight hours "
                        f"({window}). Estimated lost energy: {lost:.1f} kWh. "
                        "Readings cannot show the cause - typical checks are shading, soiling and inverter derating.")
            key = f"{a.id}:{kind}:{run[0][0]:%Y%m%d%H}"
            existing = db.scalar(select(Alert).where(Alert.dedupe_key == key))
            if existing:
                existing.severity, existing.title, existing.description = severity, title, desc
            else:
                db.add(Alert(asset_id=a.id, severity=severity, kind=kind, title=title, description=desc,
                             dedupe_key=key, created_at=run[-1][0]))
            touched += 1
    db.commit()
    return touched


# ------------------------------------------------------------------ demo seed / reset
def seed_demo(db: Session, now: datetime | None = None, with_users: bool = True) -> None:
    now = now or now_utc()
    if with_users:
        for u in DEMO_ACCOUNTS:
            if not db.scalar(select(User).where(User.email == u["email"])):
                db.add(User(email=u["email"], name=u["name"], role=u["role"], password_hash=hash_password(u["password"])))
    if not db.scalar(select(func.count()).select_from(Asset)):
        for aid, name, loc, cap, factor in DEMO_ASSETS:
            db.add(Asset(id=aid, name=name, location=loc, capacity_kw=cap, performance_factor=factor))
        db.commit()
        ensure_readings(db, now)
        # A realistic inverter derate yesterday on the smallest array, so the detector has something to find.
        inject_fault(db, "SOL-003", 0.45, hours=4, upto=floor_ist_hour(now) - timedelta(hours=24))
        detect_anomalies(db, now)
    db.commit()


def bootstrap_admin(db: Session, email: str, password: str) -> bool:
    """Create the first administrator from ADMIN_EMAIL / ADMIN_PASSWORD when no admin exists yet."""
    if not email or not password or db.scalar(select(User).where(User.role == "admin")):
        return False
    db.add(User(email=email.lower(), name="Administrator", role="admin", password_hash=hash_password(password)))
    db.commit()
    return True


def reset_demo(db: Session, now: datetime | None = None) -> None:
    db.execute(delete(Alert))
    db.execute(delete(Reading))
    db.execute(delete(Asset))
    db.commit()
    seed_demo(db, now, with_users=False)


# ------------------------------------------------------------------ dashboard
def _asset_status(alerts: list[Alert]) -> str:
    open_ = [a for a in alerts if a.acknowledged_at is None]
    if any(a.kind == "outage" for a in open_):
        return "offline"
    return "review" if open_ else "online"


def build_dashboard(db: Session, now: datetime | None = None) -> dict:
    now = now or now_utc()
    ensure_readings(db, now)
    detect_anomalies(db, now)
    end = floor_ist_hour(now)
    local_end = to_ist(end)
    today0 = local_end.replace(hour=0).astimezone(timezone.utc).replace(tzinfo=None)
    yday0 = today0 - timedelta(days=1)
    assets = db.scalars(select(Asset).order_by(Asset.id)).all()
    caps = {a.id: a.capacity_kw for a in assets}
    total_cap = sum(caps.values())

    rows = db.execute(select(Reading.asset_id, Reading.ts, Reading.power_kw)
                      .where(Reading.ts >= end - timedelta(days=HISTORY_DAYS), Reading.ts <= end).order_by(Reading.ts)).all()
    fleet: dict[datetime, float] = defaultdict(float)
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])  # actual, clear-sky over 7 days
    latest: dict[str, float] = {}
    spark: dict[str, list[float]] = defaultdict(list)
    for aid, ts, power in rows:
        if aid not in caps:
            continue
        fleet[ts] += power
        spark[aid].append(round(power, 1))
        exp = clear_sky_kw(caps[aid], to_ist(ts).hour)
        sums[aid][0] += power if exp > 0 else 0.0
        sums[aid][1] += exp
        if ts == end:
            latest[aid] = power

    hour_now = local_end.hour
    energy_today = sum(v for ts, v in fleet.items() if ts >= today0)
    y_same = sum(v for ts, v in fleet.items() if yday0 <= ts < yday0 + timedelta(hours=hour_now + 1))
    change = (energy_today - y_same) / y_same * 100 if y_same > 0 else 0.0
    r24 = [(v, clear_sky_kw(total_cap, to_ist(ts).hour)) for ts, v in fleet.items() if ts > end - timedelta(hours=24)]
    exp24 = sum(e for _, e in r24)
    performance = sum(v for v, e in r24 if e > 0) / exp24 * 100 if exp24 > 0 else 0.0
    expected_day = sum(clear_sky_kw(total_cap, h) for h in range(24))
    progress = energy_today / expected_day * 100 if expected_day > 0 else 0.0

    generation, power = [], []
    for h in range(5, 20):
        val = fleet.get(today0 + timedelta(hours=h))  # today0 = IST midnight as naive UTC
        label = f"{h:02d}:00"
        actual = round(val, 1) if val is not None else None
        generation.append({"time": label, "actual_kwh": actual, "expected_kwh": round(clear_sky_kw(total_cap, h), 1)})
        power.append({"time": label, "power_kw": actual})

    alerts_all = db.scalars(select(Alert).order_by(Alert.created_at.desc())).all()
    by_asset: dict[str, list[Alert]] = defaultdict(list)
    for al in alerts_all:
        if al.asset_id:
            by_asset[al.asset_id].append(al)
    out_assets = []
    for a in assets:
        act, exp = sums[a.id]
        out_assets.append({
            "id": a.id, "name": a.name, "location": a.location, "status": _asset_status(by_asset[a.id]),
            "power_kw": round(latest.get(a.id, 0.0), 2), "capacity_kw": a.capacity_kw,
            "efficiency": round(min(100.0, act / exp * 100), 1) if exp > 0 else 0.0,
            "spark": spark[a.id][-24:],
        })
    names = {a.id: a.name for a in assets}
    out_alerts = [alert_out(al, names) for al in alerts_all[:20]]
    return {
        "generated_at": utc(now), "timezone": "Asia/Kolkata", "demo_clock": active_demo_clock(), "demo_mode": settings.simulate_readings,
        "summary": {
            "current_power_kw": round(sum(a["power_kw"] for a in out_assets), 1),
            "energy_today_kwh": round(energy_today, 1),
            "performance_percent": round(min(100.0, performance), 1),
            "active_assets": sum(a["status"] != "offline" for a in out_assets),
            "change_percent": round(change, 1),
            "target_progress_percent": round(min(100.0, progress), 1),
        },
        "generation": generation, "power": power, "assets": out_assets, "alerts": out_alerts,
    }


def alert_out(al: Alert, names: dict[str, str]) -> dict:
    return {
        "id": al.id, "asset_id": al.asset_id, "asset_name": names.get(al.asset_id or "", None),
        "severity": al.severity, "kind": al.kind, "title": al.title, "description": al.description,
        "created_at": utc(al.created_at), "acknowledged": al.acknowledged_at is not None,
        "acknowledged_by": al.acknowledged_by,
    }


def telemetry(db: Session, hours: int, asset_id: str | None = None, now: datetime | None = None) -> list[dict]:
    now = now or now_utc()
    ensure_readings(db, now)
    end = floor_ist_hour(now)
    q = (select(Reading.ts, func.sum(Reading.power_kw), func.avg(Reading.irradiance_wm2), func.avg(Reading.temperature_c))
         .where(Reading.ts > end - timedelta(hours=hours), Reading.ts <= end).group_by(Reading.ts).order_by(Reading.ts))
    if asset_id:
        q = q.where(Reading.asset_id == asset_id)
    return [{"timestamp": utc(ts), "power_kw": round(p, 2), "energy_kwh": round(p, 2),
             "irradiance_wm2": round(i, 1), "temperature_c": round(t, 1)} for ts, p, i, t in db.execute(q).all()]


def forecast_tomorrow(db: Session, now: datetime | None = None) -> dict:
    """Average of the same local hour over the previous complete days (simple, explainable baseline)."""
    now = now or now_utc()
    ensure_readings(db, now)
    end = floor_ist_hour(now)
    local_end = to_ist(end)
    today0 = local_end.replace(hour=0).astimezone(timezone.utc).replace(tzinfo=None)
    rows = db.execute(select(Reading.ts, func.sum(Reading.power_kw)).where(Reading.ts >= today0 - timedelta(days=HISTORY_DAYS),
                      Reading.ts < today0, Reading.ts <= end).group_by(Reading.ts)).all()
    per_hour: dict[int, list[float]] = defaultdict(list)
    days = set()
    for ts, v in rows:
        local = to_ist(ts)
        per_hour[local.hour].append(v)
        days.add(local.date())
    points = [{"time": f"{h:02d}:00", "power_kw": round(sum(per_hour[h]) / len(per_hour[h]), 1) if per_hour[h] else 0.0}
              for h in range(5, 20)]
    total = sum(p["power_kw"] for p in points)
    peak = max(points, key=lambda p: p["power_kw"]) if points else {"time": "--:--", "power_kw": 0.0}
    return {"date": (local_end + timedelta(days=1)).strftime("%Y-%m-%d"), "points": points,
            "total_kwh": round(total, 1), "peak_kw": peak["power_kw"], "peak_time": peak["time"], "basis_days": len(days)}


# ------------------------------------------------------------------ analytics (visuals)
RATIO_THRESHOLD = 75.0
RATIO_MIN_HOURS = 3


def ratio_series(db: Session, asset_id: str, hours: int = 72, now: datetime | None = None) -> dict | None:
    """Per daylight hour: actual vs expected output. The same numbers the detector uses."""
    a = db.get(Asset, asset_id)
    if not a:
        return None
    now = now or now_utc()
    ensure_readings(db, now)
    end = floor_ist_hour(now)
    data = db.execute(select(Reading.ts, Reading.power_kw).where(Reading.asset_id == a.id, Reading.ts > end - timedelta(hours=hours),
                      Reading.ts <= end).order_by(Reading.ts)).all()
    points = []
    for ts, power in data:
        local = to_ist(ts)
        exp = expected_kw(a.capacity_kw, a.performance_factor, local.hour)
        if sun_shape(local.hour) > 0.2 and exp > 0:
            points.append({"timestamp": utc(ts), "label": f"{local:%a %H:%M}", "actual_kw": round(power, 2),
                           "expected_kw": round(exp, 2), "ratio_percent": round(power / exp * 100, 1)})
    return {"asset_id": a.id, "asset_name": a.name, "threshold_percent": RATIO_THRESHOLD, "min_hours": RATIO_MIN_HOURS, "points": points}


def heatmap(db: Session, days: int = 7, now: datetime | None = None) -> dict:
    """Fleet power by local day (rows) and hour (columns)."""
    now = now or now_utc()
    ensure_readings(db, now)
    end = floor_ist_hour(now)
    local_end = to_ist(end)
    start = local_end.replace(hour=0).astimezone(timezone.utc).replace(tzinfo=None) - timedelta(days=days - 1)
    cell: dict[tuple, float] = {}
    for ts, v in db.execute(select(Reading.ts, func.sum(Reading.power_kw)).where(Reading.ts >= start, Reading.ts <= end).group_by(Reading.ts)).all():
        local = to_ist(ts)
        cell[(local.date(), local.hour)] = round(v, 1)
    rows = []
    for i in range(days):
        d = local_end.date() - timedelta(days=days - 1 - i)
        rows.append({"date": d.isoformat(), "label": f"{d:%a %d}", "values": [cell.get((d, h)) for h in range(24)]})
    peak = max((v for r in rows for v in r["values"] if v is not None), default=0.0)
    return {"days": rows, "max_kw": peak}
