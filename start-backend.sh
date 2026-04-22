#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_ENV_FILE="$PROJECT_ROOT/../../.env"
UV_BIN="${UV_BIN:-/root/.local/bin/uv}"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
BACKEND_PORT="8100"

if [[ -f "$ROOT_ENV_FILE" ]]; then
  set -a
  source "$ROOT_ENV_FILE"
  set +a
fi

usage() {
  cat <<'EOF'
Usage:
  ./start-backend.sh
  ./start-backend.sh --port 8101
EOF
}

find_port_pids() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    return
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' | sed '/^$/d' || true
    return
  fi

  echo ""
}

process_matches_ocr_project() {
  local pid="$1"
  local cmdline

  cmdline="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$cmdline" == *"$PROJECT_ROOT"* ]]
}

ensure_port_available() {
  local port="$1"
  local pids
  local pid
  local remaining

  pids="$(find_port_pids "$port")"
  if [[ -z "$pids" ]]; then
    return
  fi

  echo "Backend port $port is already in use. Checking existing process..."
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    if process_matches_ocr_project "$pid"; then
      echo "Stopping existing OCR backend process on port $port (PID: $pid)"
      kill "$pid" >/dev/null 2>&1 || true
    else
      echo "Port $port is occupied by a non-OCR process (PID: $pid)." >&2
    fi
  done <<< "$pids"

  sleep 1
  remaining="$(find_port_pids "$port")"
  if [[ -n "$remaining" ]]; then
    echo "Port $port is still in use: $remaining" >&2
    echo "Please free the port or start with a different one." >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "${1}" in
    --port)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --port" >&2
        usage
        exit 1
      fi
      BACKEND_PORT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unexpected argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! [[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] || (( BACKEND_PORT < 1 || BACKEND_PORT > 65535 )); then
  echo "Invalid backend port: $BACKEND_PORT" >&2
  exit 1
fi

if ! command -v "$UV_BIN" >/dev/null 2>&1; then
  echo "uv not found at $UV_BIN" >&2
  exit 1
fi

ensure_port_available "$BACKEND_PORT"
mkdir -p "$UV_CACHE_DIR"

echo "Backend URL: http://127.0.0.1:$BACKEND_PORT"

cd "$PROJECT_ROOT"
exec env \
  UV_CACHE_DIR="$UV_CACHE_DIR" \
  PYTHONPATH="$PROJECT_ROOT" \
  "$UV_BIN" run python -m flask --app ocr_backend.app run --host 0.0.0.0 --port "$BACKEND_PORT"
