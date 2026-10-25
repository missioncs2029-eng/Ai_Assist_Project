# Security notes

## Implemented (and tested)
* **Passwords:** scrypt with per-user salt; constant-time compare.
* **Auth:** signed JWT (HS256) with expiry (`TOKEN_MINUTES`, default 8 h); invalid/expired → 401.
* **Authorisation:** admin-only endpoints return 403 for viewers (UI hides the controls as a convenience, the API enforces it).
* **Brute force:** after 8 *failed* logins in 5 min for an IP+email, further tries get 429 (successful logins are never counted, and success clears the counter).
* **Validation:** Pydantic limits on every input (lengths, ranges, list size ≤ 500); ingest rejects unknown assets, future timestamps, impossible power.
* **SQL injection:** only parameterised SQLAlchemy queries.
* **CORS:** explicit origins (+ localhost in development only), no credentials, limited methods/headers.
* **Headers:** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store` on API responses; Next.js sends the same plus `Permissions-Policy`.
* **Production guard:** `APP_ENV=production` refuses to start with a weak `JWT_SECRET`, hides demo accounts, disables demo endpoints and simulation.
* **Audit log** of sensitive actions.
* **XSS:** React escapes output; no `dangerouslySetInnerHTML` with user data.

## Known limitations (be upfront about these)
1. Token in `sessionStorage` is readable by injected scripts; HttpOnly cookies + CSRF protection are stronger.
2. No Content-Security-Policy (inline theme bootstrap script) — add nonces for production.
3. Rate limiter is in memory (per process) — use Redis behind several workers.
4. No refresh tokens, password reset, email verification or MFA.
5. Run behind HTTPS (reverse proxy / platform TLS). The repo does not terminate TLS.
6. Public registration creates *viewer* accounts; set `ALLOW_REGISTRATION=false` for closed systems.

## Security test checklist
Unauthenticated access → 401 ✔ · forged token → 401 ✔ · viewer on admin route → 403 ✔ · 9th failed login → 429 ✔ · 15 successful logins → never blocked ✔ · oversized/invalid payloads → 422 ✔ · foreign origin → no CORS header ✔ · weak production secret → refuses to start ✔ · `DEMO_CLOCK` in production → refuses to start ✔.
