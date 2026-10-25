# Change history

## v3.0 — Simple and clear
Feedback: the previous version was hard to understand, too animation-heavy, and some things looked broken. Changes:
* **Rebuilt the interface as a plain monitoring app**: sidebar, cards, tables, standard charts, six pages, plain-language labels and a “What is SolarPulse?” note. Removed the intro animation, custom cursor, page transitions, giant headlines, ribbons, glow effects, the guided tour and the other showpiece pages.
* **Fixed a real chart bug**: the “Expected (healthy plant)” line never drew (a line was placed inside an area chart). It now does, so the gap caused by a fault is visible.
* **Explains night-time zeros** with a banner, and adds an admin **demo-time** switch (`POST /api/demo/clock`, Help page) instead of needing a config file.
* Wording fixes (“1 problem needs attention”, no double negatives), relative times follow the server clock, mobile-only button no longer leaks onto desktop.
* Tests: 48 backend, 52 browser checks.

## v2.1 — Demonstration edition
Added: **How it works** page (scroll-driven pipeline, Live Lab with real API calls, interactive Detector Lab, data model, defence layers, stack, phases) · **Present** guided tour (12 steps, keyboard control, live actions) · solar-field graphic, performance gauge, CO₂ impact, asset sparklines, 7-day production heatmap · analytics endpoints · opt-in labelled `DEMO_CLOCK` for evening demos · idempotent fault injection · login limiter counts failures only. Tests: 47 backend, 65 browser checks.

## v2.0 — Product 32 full-stack prototype
Added: database (SQLAlchemy; SQLite/PostgreSQL), JWT auth with admin/viewer roles, asset CRUD, readings ingest, explainable fault detector, forecast, grounded AI assistant, audit log, CSV export, system page, demo controls, Docker/compose, Postman collection, 37 backend tests, full documentation. Removed the offline browser simulator (data now comes from the real backend).

## v1.1 — fixes to the original upload
UTC→IST daylight model · hard-coded numbers replaced by one shared model · wrong “Review” label for offline assets · `.env` never loaded · dead buttons made real · hash routing + Back button · Safari CSV download · request timeout/cancel · real timestamps · readable text sizes · localhost CORS · unused Tailwind removed · new `google_uttam_website()` design · rewritten README.

## Verified for v2.0
Backend 47/47 tests (mutation-checked) · ESLint, `tsc`, `next build` clean · 65 browser end-to-end checks (two suites) with zero console errors, incl. 390 px mobile · production-mode run (no demo data, real ingest) · Next.js standalone server run. **Not run here:** Docker, PostgreSQL.
