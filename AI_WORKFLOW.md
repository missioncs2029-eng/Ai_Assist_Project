# AI-assisted development workflow

This project was built with a generative-AI pair programmer (Claude) under human direction, following the brief’s ten phases. Use this file as your **evidence log** — replace/extend the sample entries with your own Copilot / ChatGPT / Gemini / Claude sessions and screenshots.

## Principles used
1. **Prompt with context, constraints and acceptance tests** — not “make a dashboard”.
2. **Never trust generated code unreviewed** — run it, test it, try to break it.
3. **Ask the AI to find its own bugs** — then verify with tests (mutation checks).
4. **Record what the AI got wrong** and how it was fixed.

## Prompt log (representative)
| Phase | Prompt (summary) | Outcome |
|---|---|---|
| Requirements | “Turn this brief into roles, user stories, functional and non-functional requirements for a solar monitoring platform.” | Report §1 |
| Architecture | “Design tables for users, assets, hourly readings, alerts, audit log. Constraints: SQLite now, PostgreSQL later; readings unique per asset+time.” | `models.py` |
| Backend | “FastAPI routes with JWT auth, admin/viewer roles, Pydantic validation, OpenAPI docs. Reject future timestamps and impossible power.” | `main.py`, `schemas.py` |
| AI feature | “Explainable anomaly rules (outage, underperformance) with dedupe and lost-energy estimate. No black box.” | `services.detect_anomalies` |
| Assistant | “Answer only from database results, cite figures, refuse otherwise, never invent a fault cause.” | `assistant.py` + tests |
| Testing | “Write pytest cases for auth, RBAC, rate limit, validation, detector edge cases, night time.” | 47 tests |
| Review | “Review this code for security issues and wrong assumptions.” | see below |
| Deployment | “Dockerfiles + compose with PostgreSQL, secrets from env, health checks.” | `docker-compose.yml` |

## Defects the review/testing found (and fixes)
| Found | How | Fix |
|---|---|---|
| Daylight curve used UTC → output peaked ~7 PM IST | Code review + test at local noon | Model runs in IST |
| Fake hard-coded dashboard numbers | Review | Everything derived from stored readings |
| Simulator would invent readings for real assets in production | Design review | `SIMULATE_READINGS` off in production; test added |
| Frontend on port 3001 blocked by CORS | Real-browser test | Localhost origin regex (dev only) |
| Weak dev JWT secret warning | Test log | 32+ char default; production refuses weak secrets |
| Rate limiter counted successful logins (could lock judges out during rehearsal) | Thinking through the demo, then a failing test | Count failed attempts only; success clears |
| Repeated “inject fault” compounded to zero output | Looking at the live solar-field graphic | Injection recomputes from the healthy value (idempotent) + test |
| Dashboard empty at night | Screenshot review | Opt-in, labelled `DEMO_CLOCK`; reads bounded to the clock; refused in production |
| Header overflowed with 7 nav items | Screenshot review | Responsive nav, menu below 1150 px |
| A line series placed inside an area chart never rendered (legend promised it) | Looking at the real screenshot | Use a composed chart; test now asserts both curves exist |
| Over-decorated UI hid the purpose of the app | User feedback | Rebuilt as a plain app with a one-sentence purpose on the first screen |
| Tests passing too easily | Mutation check | Broke detector/RBAC/password check → tests failed as expected |

## Human decisions (keep these in your own words in the viva)
Why rules instead of a black-box model · why SQLite first · why no external LLM · why tokens in `sessionStorage` (trade-off in `SECURITY.md`).
