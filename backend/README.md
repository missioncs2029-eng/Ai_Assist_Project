# SolarPulse backend (FastAPI)

```bash
python3 -m venv .venv            # Windows: py -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Docs: http://127.0.0.1:8000/docs · Health: `/health`. First start creates `solarpulse.db` and demo data (set `SEED_DEMO=false` to skip). Tests: `pip install -r requirements-dev.txt && python -m pytest`.

| File | Role |
|---|---|
| `app/main.py` | routes, middleware, startup |
| `app/models.py` / `db.py` | tables / engine |
| `app/services.py` | readings, anomaly detector, dashboard, forecast |
| `app/assistant.py` | grounded question answering |
| `app/security.py` | scrypt, JWT, roles, rate limiter |
| `app/solar.py` | daylight model for demo data (IST) |

PostgreSQL: `pip install -r requirements-postgres.txt` and set `DATABASE_URL`. See the root README and `docs/` for everything else.
