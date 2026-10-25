# Project Report — AI-Assisted Smart Renewable Energy Monitoring Platform (Product 32)

## 1. Requirement analysis & workflow design
**Users:** *Administrator* (plant engineer) and *Viewer* (stakeholder).
**Functional requirements:** F1 sign-in/sign-up · F2 live dashboard (power, energy, performance) · F3 history by range/asset · F4 automatic fault detection and alerts · F5 acknowledge alerts · F6 manage assets · F7 ingest readings via API · F8 forecast · F9 AI assistant · F10 CSV export · F11 audit trail.
**Non-functional:** security (auth, roles, validation), maintainability (modular, tested, typed), portability (SQLite ↔ PostgreSQL, Docker), accessibility (keyboard, reduced motion, ARIA), responsiveness (from 390 px).
**Core workflow:** readings → database → detector → alerts → admin acknowledges; assistant & charts read the same stored data.

## 2. Architecture
```
Browser (Next.js/React) ──HTTPS──▶ FastAPI ──SQLAlchemy──▶ SQLite / PostgreSQL
   JWT in sessionStorage            routes → services → models
                                    security.py (scrypt, JWT, roles, rate limit)
```
**Entities:** `users`, `assets` (1) — (N) `readings` (unique asset+timestamp), `alerts` (dedupe key), `audit_log`.
**Time:** readings are stored in UTC on whole India-Standard-Time hours; the UI displays IST.

## 3. Phase → evidence map
| Phase | Evidence |
|---|---|
| Requirement analysis | This report §1 |
| Prompt engineering & AI planning | `docs/AI_WORKFLOW.md` |
| Database & architecture | `backend/app/models.py`, §2 |
| Frontend modules | `frontend/src/views/*` (6 pages: Dashboard, Assets, Alerts, History, Assistant, Help), `components/ui.tsx` |
| Backend REST APIs | `backend/app/main.py`, Swagger at `/docs`, `docs/postman_collection.json` |
| Database integration | `services.py` (all charts read stored readings); `/api/readings` ingest |
| AI-assisted testing & debugging | `backend/tests/` (48 tests), browser E2E, mutation checks; defects in `docs/CHANGES.md` |
| Documentation & code review | README, this folder, typed schemas |
| Security testing & performance | `docs/SECURITY.md`; tests for 401/403/429, validation, CORS, scrypt |
| Cloud deployment | `Dockerfile`s, `docker-compose.yml`, `docs/DEPLOYMENT.md` |

## 4. Detection & AI features
* **Outage:** ≥ 2 consecutive daylight hours (sun > 20 %) at ≤ 0.05 kW → *critical*.
* **Underperformance:** ≥ 3 consecutive daylight hours below 75 % of `capacity × healthy factor × sun curve` → *warning* (*critical* below 30 %).
* Alerts are de-duplicated by asset + kind + start hour, include estimated lost kWh, and state that the cause cannot be seen in readings.
* **Analytics endpoints:** `/api/analytics/ratio` (the detector’s inputs) and `/api/analytics/heatmap` remain available through the API for reviewers; the simplified website does not use them.
* **Forecast:** mean of the same local hour across prior complete days.
* **Assistant:** intent matching over live database results; cites values; refuses out-of-scope questions.

## 5. Testing summary
* 48 backend tests: timezone correctness, dashboard consistency, night safety, detector rules and idempotence, status derivation, forecast, assistant grounding/refusal, auth, RBAC, rate-limit, validation, CRUD, ingest limits, CORS, production-mode safety.
* Mutation checks: deliberately breaking the detector threshold, role check and password verification each made tests fail.
* Browser E2E (real Chromium, 52 checks): sign-in page clarity, register, viewer-vs-admin UI, dashboard (chart draws both the produced area and the expected line), demo time, assets add / simulate fault / delete, alerts handle / reopen, history ranges and CSV, assistant answers and refusal, dark theme, Back button, and no horizontal scroll on a 390 px phone for every page; zero console errors.

## 6. Limitations & future work
Simulated data; baseline forecast (add weather API / ML); single-node rate limiter (use Redis); no password reset / email verification; add CSP, refresh tokens and HttpOnly cookies; CI pipeline; PostgreSQL and Docker paths were not executed in the build environment.
