#!/usr/bin/env sh
set -eu

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export STQB_HOST="$HOST"
export STQB_PORT="$PORT"
export STQB_RELOAD="false"

exec uvicorn study_qb_assistant.runtime:create_runtime_app --factory --host "$HOST" --port "$PORT" --app-dir src
