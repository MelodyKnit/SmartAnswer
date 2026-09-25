#!/usr/bin/env sh
set -eu

DEV_MODE="false"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"

# 解析命令行参数：支持 host:port、host、port 以及 --dev/-Dev 参数
for arg in "$@"; do
  case "$arg" in
    --dev|-dev|-Dev)
      DEV_MODE="true"
      ;;
    -*)
      ;;
    *)
      if [ -n "$arg" ]; then
        case "$arg" in
          *[!0-9]*)
            if echo "$arg" | grep -q ':'; then
              HOST="$(echo "$arg" | cut -d: -f1)"
              PORT="$(echo "$arg" | cut -d: -f2)"
            else
              HOST="$arg"
            fi
            ;;
          *)
            PORT="$arg"
            ;;
        esac
      fi
      ;;
  esac
done

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export STQB_HOST="$HOST"
export STQB_PORT="$PORT"

FRONTEND_ROOT="$PROJECT_ROOT/src/website"
FRONTEND_OUTPUT="$PROJECT_ROOT/src/study_qb_assistant/api/static/site"
FRONTEND_STATE="$FRONTEND_OUTPUT/.frontend-build-state"

ensure_frontend_dependencies() {
  installed_lock="$FRONTEND_ROOT/node_modules/.package-lock.json"
  package_lock="$FRONTEND_ROOT/package-lock.json"
  package_json="$FRONTEND_ROOT/package.json"
  needs_install="false"
  if [ ! -d "$FRONTEND_ROOT/node_modules" ] || [ ! -f "$installed_lock" ]; then
    needs_install="true"
  elif [ "$package_lock" -nt "$installed_lock" ] || [ "$package_json" -nt "$installed_lock" ]; then
    needs_install="true"
  fi
  if [ "$needs_install" = "false" ]; then
    return 0
  fi
  command -v npm >/dev/null 2>&1 || {
    echo "Frontend build requires npm; install Node.js/npm first." >&2
    exit 1
  }
  echo "[frontend] installing dependencies with npm ci..."
  (cd "$FRONTEND_ROOT" && npm ci --prefer-offline --no-audit --fund=false)
}

ensure_frontend_build() {
  mkdir -p "$FRONTEND_OUTPUT"
  command -v node >/dev/null 2>&1 || {
    echo "Frontend build check requires node; install Node.js first." >&2
    exit 1
  }
  fingerprint="$(node "$PROJECT_ROOT/scripts/frontend-fingerprint.mjs")"
  [ -n "$fingerprint" ] || {
    echo "Unable to calculate the frontend build fingerprint." >&2
    exit 1
  }
  previous_fingerprint=""
  if [ -f "$FRONTEND_STATE" ]; then
    previous_fingerprint="$(tr -d '\r\n' < "$FRONTEND_STATE")"
  fi
  if [ -f "$FRONTEND_OUTPUT/index.html" ] && [ "$previous_fingerprint" = "$fingerprint" ]; then
    echo "[frontend] build is up to date; skipped."
    return 0
  fi

  ensure_frontend_dependencies
  command -v npm >/dev/null 2>&1 || {
    echo "Frontend build requires npm; install Node.js/npm first." >&2
    exit 1
  }
  echo "[frontend] changes detected; building..."
  (cd "$FRONTEND_ROOT" && npm run build)
  [ -f "$FRONTEND_OUTPUT/index.html" ] || {
    echo "Frontend build completed without generating index.html." >&2
    exit 1
  }
  printf '%s\n' "$fingerprint" > "$FRONTEND_STATE"
  echo "[frontend] build completed."
}

ensure_frontend_build

if [ "$DEV_MODE" = "true" ]; then
  export STQB_RELOAD="true"
  exec python -m study_qb_assistant.bootstrap
else
  export STQB_RELOAD="false"
  exec python -m study_qb_assistant.bootstrap
fi
