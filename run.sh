#!/usr/bin/env bash
# Start the Querious server.
#
#   ./run.sh              # start on http://localhost:8000
#   ./run.sh --reload     # auto-reload on code changes (dev)
#   ./run.sh --port 9000  # any extra args pass through to uvicorn
#
set -e
cd "$(dirname "$0")"

# Activate the local virtualenv if present.
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Load .env (app also does this, but make keys available to the process early).
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

exec uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
