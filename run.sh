#!/usr/bin/env bash
# Start the Querious server.
#
#   ./run.sh              # start on the first free port at/after 8000
#   ./run.sh --reload     # auto-reload on code changes (dev)
#   PORT=9000 ./run.sh    # start scanning from a different port
#   (any other args pass through to uvicorn)
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
MAX_PORT_TRIES="${MAX_PORT_TRIES:-20}"

port_in_use() {
  # True if something is already LISTENing on the given port.
  ss -ltn 2>/dev/null | grep -q ":$1 "
}

start_port="$PORT"
tries=0
while port_in_use "$PORT"; do
  tries=$((tries + 1))
  if [ "$tries" -gt "$MAX_PORT_TRIES" ]; then
    echo "No free port found in range $start_port-$((start_port + MAX_PORT_TRIES))." >&2
    exit 1
  fi
  echo "Port $PORT is in use — trying $((PORT + 1))…"
  PORT=$((PORT + 1))
done

echo "Starting Querious on http://localhost:$PORT"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
