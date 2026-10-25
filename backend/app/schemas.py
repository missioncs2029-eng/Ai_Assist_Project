from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginIn(BaseModel):
    email: str = Field(pattern=EMAIL, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(pattern=EMAIL, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: Literal["admin", "viewer"]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AssetIn(BaseModel):
    id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{2,32}$")
    name: str = Field(min_length=2, max_length=80)
    location: str = Field(min_length=2, max_length=80)
    capacity_kw: float = Field(gt=0, le=10000)
    performance_factor: float = Field(default=0.9, ge=0.3, le=1.0)


class AssetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    location: str | None = Field(default=None, min_length=2, max_length=80)
    capacity_kw: float | None = Field(default=None, gt=0, le=10000)
    performance_factor: float | None = Field(default=None, ge=0.3, le=1.0)


class AssetOut(BaseModel):
    id: str
    name: str
    location: str
    status: Literal["online", "review", "offline"]
    power_kw: float
    capacity_kw: float
    efficiency: float
    spark: list[float] = []


class AlertOut(BaseModel):
    id: int
    asset_id: str | None
    asset_name: str | None
    severity: Literal["critical", "warning", "info"]
    kind: str
    title: str
    description: str
    created_at: datetime
    acknowledged: bool
    acknowledged_by: str | None


class Summary(BaseModel):
    current_power_kw: float
    energy_today_kwh: float
    performance_percent: float
    active_assets: int
    change_percent: float
    target_progress_percent: float


class GenerationPoint(BaseModel):
    time: str
    actual_kwh: float | None
    expected_kwh: float


class PowerPoint(BaseModel):
    time: str
    power_kw: float | None


class DashboardOut(BaseModel):
    generated_at: datetime
    timezone: str
    demo_clock: str | None = None
    demo_mode: bool = False
    summary: Summary
    generation: list[GenerationPoint]
    power: list[PowerPoint]
    assets: list[AssetOut]
    alerts: list[AlertOut]


class TelemetryOut(BaseModel):
    timestamp: datetime
    power_kw: float
    energy_kwh: float
    irradiance_wm2: float
    temperature_c: float


class ForecastOut(BaseModel):
    date: str
    points: list[PowerPoint]
    total_kwh: float
    peak_kw: float
    peak_time: str
    basis_days: int


class ReadingIn(BaseModel):
    asset_id: str = Field(max_length=32)
    ts: datetime
    power_kw: float = Field(ge=0, le=100000)
    irradiance_wm2: float = Field(default=0, ge=0, le=1500)
    temperature_c: float = Field(default=25, ge=-50, le=100)


class IngestIn(BaseModel):
    readings: list[ReadingIn] = Field(min_length=1, max_length=500)


class IngestOut(BaseModel):
    inserted: int
    updated: int


class AssistantIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class SourceOut(BaseModel):
    label: str
    value: str


class AssistantOut(BaseModel):
    intent: str
    answer: str
    sources: list[SourceOut]


class FaultIn(BaseModel):
    asset_id: str = Field(max_length=32)
    ratio: float = Field(default=0.45, ge=0.0, le=0.9)
    hours: int = Field(default=4, ge=3, le=8)


class ClockIn(BaseModel):
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class AuditOut(BaseModel):
    ts: datetime
    actor: str
    action: str
    detail: str


class SystemOut(BaseModel):
    version: str
    environment: str
    database: str
    users: int
    assets: int
    readings: int
    alerts: int
    open_alerts: int
    latest_reading: datetime | None


class RatioPoint(BaseModel):
    timestamp: datetime
    label: str
    actual_kw: float
    expected_kw: float
    ratio_percent: float


class RatioOut(BaseModel):
    asset_id: str
    asset_name: str
    threshold_percent: float
    min_hours: int
    points: list[RatioPoint]


class HeatRow(BaseModel):
    date: str
    label: str
    values: list[float | None]


class HeatmapOut(BaseModel):
    days: list[HeatRow]
    max_kw: float
