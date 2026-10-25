# Deployment guide

> The Dockerfiles and compose file were written carefully but **not executed** in the build environment (no Docker there). The pieces they rely on *were* verified: PostgreSQL-neutral SQLAlchemy code, the Next.js standalone server, production-mode behaviour of the API. Run `docker compose up --build` once and fix anything environment-specific.

## 1. Docker Compose (API + web + PostgreSQL)
```bash
cp .env.docker.example .env
# edit .env: DB_PASSWORD, JWT_SECRET (python -c "import secrets;print(secrets.token_urlsafe(48))"), ADMIN_EMAIL, ADMIN_PASSWORD
docker compose up --build
```
Open http://localhost:3000 · API docs http://localhost:8000/docs.

**Public demo instead of real data:** in `.env` set `APP_ENV=development` and `SEED_DEMO=true` (one-click demo accounts and simulated data — never mix with real data).

## 2. Connecting real data
In production there is no simulator. Create assets (UI or `POST /api/assets`), then post hourly readings:
```bash
curl -X POST $API/api/readings -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"readings":[{"asset_id":"SOL-001","ts":"2026-10-20T06:30:00Z","power_kw":12.4,"irradiance_wm2":640,"temperature_c":31}]}'
```
Timestamps should be on whole India-Standard-Time hours (:30 UTC). The detector runs after every ingest.

## 3. Hosted options (outline)
| Part | Example | Notes |
|---|---|---|
| Database | Neon / Supabase / Render PostgreSQL | set `DATABASE_URL=postgresql+psycopg://…` |
| API | Render / Railway / Fly.io from `backend/Dockerfile` | set env vars from `.env.example`; health check `/health` |
| Web | Vercel / Netlify / the `frontend/Dockerfile` | build arg / env `NEXT_PUBLIC_API_URL=https://your-api` |
| CORS | set `FRONTEND_ORIGIN=https://your-web-domain` on the API | |

## 4. Pre-launch checklist
- [ ] Strong `JWT_SECRET`, `APP_ENV=production`, `SEED_DEMO=false`
- [ ] HTTPS everywhere; `FRONTEND_ORIGIN` set to the real site
- [ ] `ALLOW_REGISTRATION=false` if closed
- [ ] Database backups; change default DB password
- [ ] Read `docs/SECURITY.md` known limitations
