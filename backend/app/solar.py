"""Physical model used to SEED and EXTEND demo data. Times are India Standard Time (IST).

Real deployments replace this with inverter / meter feeds posted to POST /api/readings.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")
CLEAR_SKY = 0.95  # fraction of nameplate a perfect, clean array delivers at solar noon


def to_ist(ts: datetime) -> datetime:
    """Stored naive-UTC datetime -> aware IST datetime."""
    return ts.replace(tzinfo=timezone.utc).astimezone(IST)


def sun_shape(hour: float) -> float:
    """0..1 daylight curve: sunrise 06:00, noon peak, sunset 18:00."""
    return 0.0 if hour <= 6.0 or hour >= 18.0 else math.sin(math.pi * (hour - 6.0) / 12.0)


def weather(day: int, hour: float) -> float:
    """Deterministic 'cloud' factor 0.94..1.0."""
    return 0.97 + 0.03 * math.sin(day * 1.3 + hour * 0.9)


def expected_kw(capacity: float, factor: float, hour: float) -> float:
    """What a healthy asset should produce (no weather)."""
    return capacity * factor * sun_shape(hour)


def clear_sky_kw(capacity: float, hour: float) -> float:
    return capacity * CLEAR_SKY * sun_shape(hour)


def simulate(capacity: float, factor: float, ts_utc: datetime) -> tuple[float, float, float]:
    """(power_kw, irradiance_wm2, temperature_c) for one asset at a stored UTC timestamp."""
    local = to_ist(ts_utc)
    hour, day = local.hour + local.minute / 60, local.timetuple().tm_yday
    sun, w = sun_shape(hour), weather(local.timetuple().tm_yday, hour)
    power = round(capacity * factor * sun * w, 2)
    irr = round(1000.0 * sun * w, 1)
    temp = round(24.0 + 9.0 * sun + 1.5 * math.sin((hour - 9) / 24 * 2 * math.pi), 1)
    return power, irr, temp


def floor_ist_hour(now_utc_naive: datetime) -> datetime:
    """Latest whole IST hour as naive UTC."""
    local = to_ist(now_utc_naive).replace(minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).replace(tzinfo=None)
