#!/usr/bin/env bash
# SolarPulse one-command setup + start (macOS / Linux).  Usage:  bash start.sh
set -e
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1; }
command -v npm >/dev/null || { echo "Node.js 20.9+ is required: https://nodejs.org/"; exit 1; }

echo "==> Setting up the backend (first run takes a minute)"
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -q --upgrade pip
backend/.venv/bin/python -m pip install -q -r backend/requirements.txt

echo "==> Setting up the frontend"
[ -f frontend/.env.local ] || cp frontend/.env.example frontend/.env.local
(cd frontend && npm install --no-audit --no-fund)

echo "==> Starting SolarPulse:  web http://localhost:3000   api http://127.0.0.1:8000/docs   (Ctrl+C stops both)"
trap 'kill 0' EXIT INT TERM
(cd backend && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
(cd frontend && npm run dev) &
wait
