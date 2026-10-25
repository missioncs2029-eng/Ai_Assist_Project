"""Settings read from environment variables (and backend/.env if present)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DEFAULT_SECRET = "dev-only-change-me-dev-only-change-me"


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development").lower()
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'solarpulse.db'}")
    jwt_secret: str = os.getenv("JWT_SECRET", DEFAULT_SECRET)
    token_minutes: int = int(os.getenv("TOKEN_MINUTES", "480"))
    seed_demo: bool = _bool("SEED_DEMO", True)
    allow_registration: bool = _bool("ALLOW_REGISTRATION", True)
    # Simulated readings are for demos only. In production real readings arrive via POST /api/readings.
    simulate_readings: bool = _bool("SIMULATE_READINGS", os.getenv("APP_ENV", "development").lower() != "production")
    # Demo only: pin the simulated time of day (IST), e.g. "12:30", so a demo at night still shows sunshine.
    demo_clock: str = os.getenv("DEMO_CLOCK", "").strip()
    admin_email: str = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate(self) -> None:
        if self.is_production and (self.jwt_secret == DEFAULT_SECRET or len(self.jwt_secret) < 32):
            raise RuntimeError("APP_ENV=production requires JWT_SECRET to be set to a random value of 32+ characters.")
        if self.demo_clock:
            if self.is_production:
                raise RuntimeError("DEMO_CLOCK must not be set when APP_ENV=production.")
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", self.demo_clock):
                raise RuntimeError('DEMO_CLOCK must look like "HH:MM" (India time), e.g. "12:30".')
        if self.admin_password and len(self.admin_password) < 10:
            raise RuntimeError("ADMIN_PASSWORD must be at least 10 characters.")


settings = Settings()
