from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import settings
from .db import Base
from .solar import IST


_clock = {"value": None}  # runtime override set from the UI (demo only); None = use env / real time


def set_demo_clock(value: str | None) -> None:
    _clock["value"] = value


def active_demo_clock() -> str | None:
    return _clock["value"] or settings.demo_clock or None


def now_utc() -> datetime:
    """Naive UTC (databases store naive; we always treat stored values as UTC).
    With DEMO_CLOCK="HH:MM" the India time of day is pinned (today's date) - for demos only."""
    real = datetime.now(timezone.utc)
    clock = active_demo_clock()
    if clock:
        h, m = (int(x) for x in clock.split(":"))
        real = real.astimezone(IST).replace(hour=h, minute=m, second=0, microsecond=0).astimezone(timezone.utc)
    return real.replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(16), default="viewer")  # admin | viewer
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(String(80))
    capacity_kw: Mapped[float] = mapped_column(Float)
    performance_factor: Mapped[float] = mapped_column(Float, default=0.9)  # healthy expectation, 0.3 - 1.0
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    readings: Mapped[list["Reading"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (UniqueConstraint("asset_id", "ts", name="uq_reading_asset_ts"), Index("ix_reading_ts", "ts"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)  # UTC, on whole IST hours
    power_kw: Mapped[float] = mapped_column(Float)
    irradiance_wm2: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    asset: Mapped[Asset] = relationship(back_populates="readings")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    severity: Mapped[str] = mapped_column(String(12))  # critical | warning | info
    kind: Mapped[str] = mapped_column(String(24))  # underperformance | outage
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    acknowledged_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)
    actor: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(300), default="")
