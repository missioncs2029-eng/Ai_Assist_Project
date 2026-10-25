# ☀️ SolarPulse — Solar Plant Monitoring System

**What is it?** A website that watches solar panels for you.

- **See** how much electricity the plant is producing, hour by hour.
- **Get warned** automatically when a panel group produces much less than it should.
- **Ask** questions in plain English, like “How much energy today?”

It is a working prototype for **Product 32: AI-Assisted Smart Renewable Energy Monitoring Platform**. The panel readings are **simulated**; everything else (login, database, fault detector, charts, assistant) is real and tested.

| | |
|---|---|
| Frontend | Next.js 15, React, TypeScript, Recharts |
| Backend | Python, FastAPI, SQLAlchemy, JWT login with roles |
| Database | SQLite (no setup) or PostgreSQL |
| Checked with | 48 backend tests · 52 browser checks · ESLint · TypeScript |

---

## 1. Run it (3 minutes)

**Install two free programs first (once):** [Node.js 20.9+ (LTS)](https://nodejs.org) and [Python 3.10+](https://www.python.org/downloads/). On Windows tick **“Add python.exe to PATH”**. Restart your terminal afterwards.

| Your computer | Do this |
|---|---|
| **Windows** | Unzip, then double-click **`start-windows.bat`** |
| **Mac / Linux** | In the folder run: `bash start.sh` |

The first run installs everything (1–3 minutes). Then open **http://localhost:3000**. To stop: close the two black windows (Windows) or press `Ctrl+C`.

On the sign-in page, press **Administrator** under “Use a demo account”. No sign-up needed.

<details><summary>Manual start (two terminals)</summary>

```powershell
# Terminal 1 - backend (Windows PowerShell)
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 - frontend
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```
```bash
# Terminal 1 - backend (Mac / Linux)
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 - frontend
cd frontend && cp .env.example .env.local && npm install && npm run dev
```
</details>

| Demo account | Email | Password | Can do |
|---|---|---|---|
| Administrator | `admin@solarpulse.demo` | `Admin@12345` | Everything: add assets, mark alerts handled, demo tools |
| Viewer | `viewer@solarpulse.demo` | `Viewer@12345` | Look only |

---

## 2. The six pages

| Page | What it is for |
|---|---|
| **Dashboard** | The big picture: power now, energy today, performance, a chart of today versus a healthy plant, your assets and recent alerts. |
| **Assets** | The list of solar panel groups with status, power, efficiency and a 24-hour mini chart. Admins can add or delete assets. |
| **Alerts** | Problems found automatically, with the time, the shortfall and the energy lost. Admins mark them as handled. |
| **History** | Power over 24 hours, 3 days or 7 days (all assets or one), sunlight and temperature, tomorrow’s estimate, CSV download. |
| **Assistant** | Ask questions. It answers only from stored data, shows the numbers it used, and says “I won’t guess” when it can’t answer. |
| **Help** | What the app does, what kW and kWh mean, how it works, demo tools, live server information, audit log, API documentation link. |

**Good to know**
- **At night the panels produce 0 kW. That is correct**, not a bug (India sunrise ≈ 6 AM, sunset ≈ 6 PM). The Dashboard says so and, for admins in the demo, offers **“Show midday data”**. You can also use **Help → Demo tools → Show midday / Use real time**.
- Status words: **Working**, **Needs attention** (clearly below expected for several daylight hours), **Not producing** (almost nothing while the sun is up).

---

## 3. A 5-minute demo for the judges

1. **Sign in** as Administrator. Say: *“This monitors solar panels. Login is real: hashed passwords, tokens, roles.”*
2. **Dashboard** — point at the four numbers and the chart. *“Orange is what we produced, dotted grey is what a healthy plant would make.”* (At night, press **Show midday data** first.)
3. **Alerts** — *“The detector already found a panel group producing too little, and estimated the energy lost.”*
4. **Assets → Simulate fault** on any asset, then open **Alerts**. *“It reacts to the stored readings; nothing is hard-coded.”* Press **Mark as handled**.
5. **Assistant** — ask *“Are there any problems?”* then *“Who will win the cricket match?”* *“It uses only our data and refuses to guess.”*
6. **History** — switch to 7 days, pick one asset, show tomorrow’s estimate, press **Export CSV**.
7. **Help** — show the database count, the audit log and the **API documentation (Swagger)**.
8. **Sign out → Viewer** — Add/Delete buttons are gone and the API answers *403*. *“Role-based security.”*

**Common questions** — *Is the data real?* Simulated; real readings plug into `POST /api/readings`. *Is the AI a black box?* No: two written rules plus a baseline forecast, and an assistant that cites its numbers (`docs/AI_ETHICS.md`). *How is it secured?* `docs/SECURITY.md`. *How would you deploy it?* `docs/DEPLOYMENT.md`.

---

## 4. How it works (plain English)

```
 Solar panels ──hourly readings──▶ API (FastAPI) ──▶ Database ──▶ Fault detector ──▶ Alerts
                                                        │
                                                        └──▶ Dashboard · History · Assistant (Next.js website)
```

- **Fault detector.** *Outage*: 2+ daylight hours at about 0 kW. *Underperformance*: 3+ daylight hours below 75% of what that asset should deliver. Each alert states the numbers and says the cause must be checked on site.
- **Tomorrow’s estimate.** The average of the same hours over the previous days. A baseline, not a weather forecast.
- **Assistant.** Reads the same database, answers with figures, never invents a cause.

```
solar-monitor/
├── start.sh · start-windows.bat · docker-compose.yml
├── backend/   app/main.py (API) · services.py (detector, dashboard) · assistant.py · security.py · models.py   tests/ (48)
├── frontend/  src/app/page.tsx (layout) · src/views/ (6 pages) · src/components/ui.tsx · src/lib/api.ts
└── docs/      PROJECT_REPORT · AI_WORKFLOW · AI_ETHICS · SECURITY · DEPLOYMENT · CHANGES · postman_collection.json
```

### API (interactive docs at http://127.0.0.1:8000/docs)
| Endpoint | Who | Purpose |
|---|---|---|
| `POST /api/auth/login` · `/register` | public | sign in / sign up |
| `GET /api/dashboard` `/telemetry` `/forecast` `/alerts` `/assets` | signed in | monitoring data |
| `POST /api/assistant` · `GET /api/export/readings.csv` | signed in | questions · download |
| `POST/PATCH/DELETE /api/assets` · `POST /api/alerts/{id}/ack` | admin | manage assets, mark alerts handled |
| `POST /api/readings` | admin | send real readings (max 500 per call) |
| `GET /api/audit` · `POST /api/demo/fault` `/demo/clock` `/demo/reset` | admin | audit log, demo tools |
| `GET /health` · `GET /api/system` | public / signed in | health, live stats |

---

## 5. Settings (optional — defaults work)

`backend/.env` (copy `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | SQLite file | PostgreSQL: `postgresql+psycopg://user:pass@host/db` (`pip install -r requirements-postgres.txt`) |
| `JWT_SECRET` | dev value | **Set a long random secret in production** |
| `APP_ENV` | `development` | `production` hides demo accounts/tools and stops simulation |
| `SEED_DEMO` | `true` | Create demo users, assets and 7 days of readings |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | – | First admin for a real deployment |
| `DEMO_CLOCK` | – | e.g. `12:30` pins the simulated time of day (demo only) |

`frontend/.env.local`: `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`; restart the frontend after editing).

## 6. Check the code yourself
```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest        # 48 tests
cd frontend && npm run lint && npm run typecheck && npm run build
```
Import `docs/postman_collection.json` into Postman for ready-made API calls. Docker: `cp .env.docker.example .env`, edit it, `docker compose up --build` (see `docs/DEPLOYMENT.md`; not run in the build environment).

## 7. Troubleshooting
| Problem | Fix |
|---|---|
| “Can’t reach the server” | The backend isn’t running. Open http://127.0.0.1:8000/health. Check `frontend/.env.local` and restart the frontend. |
| Everything shows 0 kW | It is night in India. Use **Show midday data** (Dashboard banner or Help → Demo tools). |
| `node` / `npm` / `python` not found | Install them (section 1) and **restart the terminal / VS Code**. |
| PowerShell blocks `Activate.ps1` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| “Too many failed attempts” | Only wrong passwords count. Wait 5 minutes or restart the backend. |
| Want fresh demo data | Help → Demo tools → **Reset demo data**, or stop the backend and delete `backend/solarpulse.db`. |
| “Port already in use” | Close the old window using it (Next.js may move to 3001, which still works). |
| Odd styles after updating | Stop, delete `frontend/.next`, run again. |

If something still looks wrong, copy the **red error text** from the terminal or the message on screen; it usually names the exact problem.

## 8. Honest limits
A prototype, not a certified production system: simulated panel data, a single-server in-memory rate limiter, login tokens kept per browser tab, no email verification or password reset, TLS must be provided in front of it. Details: `docs/SECURITY.md`.
