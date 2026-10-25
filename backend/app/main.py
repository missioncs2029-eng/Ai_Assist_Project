"""SolarPulse API - AI-Assisted Smart Renewable Energy Monitoring Platform."""
from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import assistant, schemas
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import Alert, Asset, AuditLog, Reading, User, now_utc, set_demo_clock
from .security import admin_only, create_token, current_user, hash_password, login_limiter, verify_password
from .services import (DEMO_ACCOUNTS, alert_out, audit, bootstrap_admin, build_dashboard, detect_anomalies, ensure_readings, forecast_tomorrow,
                       heatmap, inject_fault, ratio_series, reset_demo, seed_demo, telemetry, utc)
from .solar import floor_ist_hour

VERSION = "3.0.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if settings.seed_demo:
            seed_demo(db)
        bootstrap_admin(db, settings.admin_email, settings.admin_password)
    yield


app = FastAPI(
    title="SolarPulse API",
    description="REST API for the AI-assisted smart renewable energy monitoring platform. "
                "Click **Authorize** and sign in with a demo account to try the endpoints. Demo data is simulated.",
    version=VERSION,
    lifespan=lifespan,
)


def _origins() -> list[str]:
    found = [o.strip().rstrip("/") for o in settings.frontend_origin.split(",") if o.strip()]
    return list(dict.fromkeys(found + ["http://localhost:3000", "http://127.0.0.1:3000"]))


app.add_middleware(
    CORSMiddleware, allow_origins=_origins(),
    allow_origin_regex=None if settings.is_production else r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _user_out(u: User) -> schemas.UserOut:
    return schemas.UserOut(id=u.id, email=u.email, name=u.name, role=u.role)  # type: ignore[arg-type]


def _login(db: Session, email: str, password: str, request: Request) -> User:
    email = email.strip().lower()
    key = f"{request.client.host if request.client else '?'}:{email}"
    login_limiter.check(key)
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(password, user.password_hash):
        login_limiter.fail(key)
        audit(db, email, "login_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    login_limiter.clear(key)
    audit(db, email, "login")
    return user


# ------------------------------------------------------------------ public
@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": "SolarPulse API", "docs": "/docs", "health": "/health", "version": VERSION}


@app.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": VERSION, "database": engine.dialect.name}


@app.get("/api/auth/demo-accounts", tags=["auth"])
def demo_accounts() -> list[dict[str, str]]:
    """One-click demo sign-in. Disabled automatically when APP_ENV=production or SEED_DEMO=false."""
    if settings.is_production or not settings.seed_demo:
        return []
    return [{"email": u["email"], "password": u["password"], "role": u["role"], "name": u["name"]} for u in DEMO_ACCOUNTS]


# ------------------------------------------------------------------ auth
@app.post("/api/auth/login", response_model=schemas.TokenOut, tags=["auth"])
def login(body: schemas.LoginIn, request: Request, db: Session = Depends(get_db)):
    user = _login(db, body.email, body.password, request)
    return schemas.TokenOut(access_token=create_token(user), user=_user_out(user))


@app.post("/api/auth/token", tags=["auth"], summary="OAuth2 form login (used by the Swagger Authorize button)")
def token(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = _login(db, form.username, form.password, request)
    return {"access_token": create_token(user), "token_type": "bearer"}


@app.post("/api/auth/register", response_model=schemas.TokenOut, status_code=201, tags=["auth"])
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled")
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, name=body.name.strip(), role="viewer", password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    audit(db, email, "register")
    return schemas.TokenOut(access_token=create_token(user), user=_user_out(user))


@app.get("/api/auth/me", response_model=schemas.UserOut, tags=["auth"])
def me(user: User = Depends(current_user)):
    return _user_out(user)


# ------------------------------------------------------------------ monitoring (any signed-in user)
@app.get("/api/dashboard", response_model=schemas.DashboardOut, tags=["monitoring"])
def get_dashboard(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return build_dashboard(db)


@app.get("/api/telemetry", response_model=list[schemas.TelemetryOut], tags=["monitoring"])
def get_telemetry(hours: int = Query(default=24, ge=1, le=168), asset_id: str | None = Query(default=None, max_length=32),
                  _: User = Depends(current_user), db: Session = Depends(get_db)):
    return telemetry(db, hours, asset_id)


@app.get("/api/forecast", response_model=schemas.ForecastOut, tags=["monitoring"])
def get_forecast(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return forecast_tomorrow(db)


@app.get("/api/analytics/ratio", response_model=schemas.RatioOut, tags=["analytics"],
         summary="Actual vs expected output per daylight hour (what the detector sees)")
def analytics_ratio(asset_id: str = Query(max_length=32), hours: int = Query(default=72, ge=24, le=168),
                    _: User = Depends(current_user), db: Session = Depends(get_db)):
    out = ratio_series(db, asset_id, hours)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return out


@app.get("/api/analytics/heatmap", response_model=schemas.HeatmapOut, tags=["analytics"], summary="Fleet power by day and hour")
def analytics_heatmap(days: int = Query(default=7, ge=3, le=14), _: User = Depends(current_user), db: Session = Depends(get_db)):
    return heatmap(db, days)


@app.get("/api/export/readings.csv", tags=["monitoring"])
def export_csv(hours: int = Query(default=24, ge=1, le=168), _: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_readings(db)
    end = floor_ist_hour(now_utc())
    rows = db.execute(select(Reading.ts, Reading.asset_id, Reading.power_kw, Reading.irradiance_wm2, Reading.temperature_c)
                      .where(Reading.ts > end - timedelta(hours=hours), Reading.ts <= end).order_by(Reading.ts, Reading.asset_id)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp_utc", "asset_id", "power_kw", "irradiance_wm2", "temperature_c"])
    for ts, aid, p, i, t in rows:
        w.writerow([utc(ts).isoformat(), aid, p, i, t])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="solarpulse-readings-{hours}h.csv"'})


@app.get("/api/alerts", response_model=list[schemas.AlertOut], tags=["alerts"])
def list_alerts(open_only: bool = False, _: User = Depends(current_user), db: Session = Depends(get_db)):
    build_dashboard(db)  # makes sure readings are current and detection has run
    q = select(Alert).order_by(Alert.created_at.desc()).limit(200)
    if open_only:
        q = q.where(Alert.acknowledged_at.is_(None))
    names = {a.id: a.name for a in db.scalars(select(Asset)).all()}
    return [alert_out(a, names) for a in db.scalars(q).all()]


def _alert_or_404(db: Session, alert_id: int) -> Alert:
    al = db.get(Alert, alert_id)
    if not al:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return al


@app.post("/api/alerts/{alert_id}/ack", response_model=schemas.AlertOut, tags=["alerts"])
def ack_alert(alert_id: int, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    al = _alert_or_404(db, alert_id)
    al.acknowledged_by, al.acknowledged_at = user.email, now_utc()
    db.commit()
    audit(db, user.email, "alert_ack", f"alert {alert_id}")
    return alert_out(al, {a.id: a.name for a in db.scalars(select(Asset)).all()})


@app.post("/api/alerts/{alert_id}/unack", response_model=schemas.AlertOut, tags=["alerts"])
def unack_alert(alert_id: int, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    al = _alert_or_404(db, alert_id)
    al.acknowledged_by = al.acknowledged_at = None
    db.commit()
    audit(db, user.email, "alert_unack", f"alert {alert_id}")
    return alert_out(al, {a.id: a.name for a in db.scalars(select(Asset)).all()})


# ------------------------------------------------------------------ assets
@app.get("/api/assets", response_model=list[schemas.AssetOut], tags=["assets"])
def list_assets(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return build_dashboard(db)["assets"]


def _asset_out(db: Session, asset_id: str) -> dict:
    return next(a for a in build_dashboard(db)["assets"] if a["id"] == asset_id)


@app.post("/api/assets", response_model=schemas.AssetOut, status_code=201, tags=["assets"])
def create_asset(body: schemas.AssetIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    aid = body.id
    if not aid:
        n = db.scalar(select(func.count()).select_from(Asset)) or 0
        aid = f"SOL-{n + 1:03d}"
        while db.get(Asset, aid):
            n += 1
            aid = f"SOL-{n + 1:03d}"
    if db.get(Asset, aid):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Asset {aid} already exists")
    db.add(Asset(id=aid, name=body.name.strip(), location=body.location.strip(),
                 capacity_kw=body.capacity_kw, performance_factor=body.performance_factor))
    db.commit()
    audit(db, user.email, "asset_create", aid)
    return _asset_out(db, aid)


@app.patch("/api/assets/{asset_id}", response_model=schemas.AssetOut, tags=["assets"])
def update_asset(asset_id: str, body: schemas.AssetPatch, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(a, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    audit(db, user.email, "asset_update", asset_id)
    return _asset_out(db, asset_id)


@app.delete("/api/assets/{asset_id}", status_code=204, tags=["assets"])
def delete_asset(asset_id: str, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    for al in db.scalars(select(Alert).where(Alert.asset_id == asset_id)).all():
        db.delete(al)
    db.delete(a)
    db.commit()
    audit(db, user.email, "asset_delete", asset_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ data ingest (admin / integration)
@app.post("/api/readings", response_model=schemas.IngestOut, status_code=201, tags=["ingest"],
          summary="Post real readings from an inverter or gateway")
def ingest(body: schemas.IngestIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    ensure_readings(db)
    limit = now_utc() + timedelta(hours=1)
    assets = {a.id: a for a in db.scalars(select(Asset)).all()}
    inserted = updated = 0
    for r in body.readings:
        a = assets.get(r.asset_id)
        if not a:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown asset {r.asset_id}")
        ts = r.ts if r.ts.tzinfo is None else r.ts.astimezone(timezone.utc).replace(tzinfo=None)
        if ts > limit:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Reading timestamp is in the future")
        if r.power_kw > a.capacity_kw * 1.5:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"power_kw exceeds 150% of {a.id} capacity")
        ts = ts.replace(minute=0, second=0, microsecond=0) if ts.minute == 0 else ts
        existing = db.scalar(select(Reading).where(Reading.asset_id == a.id, Reading.ts == ts))
        if existing:
            existing.power_kw, existing.irradiance_wm2, existing.temperature_c = r.power_kw, r.irradiance_wm2, r.temperature_c
            updated += 1
        else:
            db.add(Reading(asset_id=a.id, ts=ts, power_kw=r.power_kw, irradiance_wm2=r.irradiance_wm2, temperature_c=r.temperature_c))
            inserted += 1
    db.commit()
    detect_anomalies(db)
    audit(db, user.email, "ingest", f"{inserted} new, {updated} updated")
    return schemas.IngestOut(inserted=inserted, updated=updated)


# ------------------------------------------------------------------ AI assistant
@app.post("/api/assistant", response_model=schemas.AssistantOut, tags=["ai"])
def ask(body: schemas.AssistantIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return assistant.answer(db, body.question)


# ------------------------------------------------------------------ demo controls & system
def _demo_only() -> None:
    if settings.is_production:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not available in production")


@app.post("/api/demo/fault", tags=["demo"], summary="Inject a fault so you can watch the detector react")
def demo_fault(body: schemas.FaultIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    _demo_only()
    if not db.get(Asset, body.asset_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    ensure_readings(db)
    n = inject_fault(db, body.asset_id, body.ratio, body.hours)
    found = detect_anomalies(db)
    audit(db, user.email, "demo_fault", f"{body.asset_id} x{body.ratio} for {n}h")
    return {"hours_modified": n, "alerts_checked": found}


@app.post("/api/demo/clock", tags=["demo"], summary="Pin the simulated India time of day (e.g. 12:30), or null for real time")
def demo_clock(body: schemas.ClockIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    _demo_only()
    set_demo_clock(body.time)
    audit(db, user.email, "demo_clock", body.time or "real time")
    return {"demo_clock": body.time}


@app.post("/api/demo/reset", tags=["demo"], summary="Restore the original demo data")
def demo_reset(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    _demo_only()
    reset_demo(db)
    audit(db, user.email, "demo_reset")
    return {"status": "reset"}


@app.get("/api/system", response_model=schemas.SystemOut, tags=["system"])
def system(_: User = Depends(current_user), db: Session = Depends(get_db)):
    count = lambda m: db.scalar(select(func.count()).select_from(m)) or 0  # noqa: E731
    latest = db.scalar(select(func.max(Reading.ts)))
    return schemas.SystemOut(
        version=VERSION, environment=settings.app_env, database=engine.dialect.name, users=count(User), assets=count(Asset),
        readings=count(Reading), alerts=count(Alert),
        open_alerts=db.scalar(select(func.count()).select_from(Alert).where(Alert.acknowledged_at.is_(None))) or 0,
        latest_reading=utc(latest) if latest else None)


@app.get("/api/audit", response_model=list[schemas.AuditOut], tags=["system"])
def audit_trail(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [{"ts": utc(a.ts), "actor": a.actor, "action": a.action, "detail": a.detail}
            for a in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(50)).all()]
