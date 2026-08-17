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

if [ "$DEV_MODE" = "true" ]; then
  export STQB_RELOAD="true"
  exec python -m study_qb_assistant.bootstrap
else
  export STQB_RELOAD="false"
  exec python -m study_qb_assistant.bootstrap
fi
