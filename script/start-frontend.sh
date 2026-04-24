#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/ocr_frontend"
FRONTEND_CONFIG_FILE="$FRONTEND_DIR/config.js"
FRONTEND_SERVER="$FRONTEND_DIR/server.py"
ROOT_ENV_FILE="$PROJECT_ROOT/../../.env"
BACKEND_PORT="8100"
FRONTEND_PORT="8080"
API_HOST="${API_HOST:-}"

if [[ -f "$ROOT_ENV_FILE" ]]; then
  set -a
  source "$ROOT_ENV_FILE"
  set +a
fi

usage() {
  cat <<'EOF'
Usage:
  ./script/start-frontend.sh
  ./script/start-frontend.sh --backend-port 8101 --port 8081
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

  echo "Frontend port $port is already in use. Checking existing process..."
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    if process_matches_ocr_project "$pid"; then
      echo "Stopping existing OCR frontend process on port $port (PID: $pid)"
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
    --backend-port)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --backend-port" >&2
        usage
        exit 1
      fi
      BACKEND_PORT="$2"
      shift 2
      ;;
    --port)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --port" >&2
        usage
        exit 1
      fi
      FRONTEND_PORT="$2"
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

if ! [[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] || (( FRONTEND_PORT < 1 || FRONTEND_PORT > 65535 )); then
  echo "Invalid frontend port: $FRONTEND_PORT" >&2
  exit 1
fi

if [[ -z "$API_HOST" ]]; then
  if command -v hostname >/dev/null 2>&1; then
    HOST_IPS="$(hostname -I 2>/dev/null || true)"
    for candidate in $HOST_IPS; do
      if [[ "$candidate" != 127.* ]] && [[ "$candidate" != "::1" ]]; then
        API_HOST="$candidate"
        break
      fi
    done
  fi
  API_HOST="${API_HOST:-127.0.0.1}"
fi

cat > "$FRONTEND_CONFIG_FILE" <<EOF
window.OCR_APP_CONFIG = {
  apiBaseUrl: "http://$API_HOST:$BACKEND_PORT"
};
EOF

ensure_port_available "$FRONTEND_PORT"

echo "Backend URL for frontend: http://$API_HOST:$BACKEND_PORT"
echo "Frontend URL: http://$API_HOST:$FRONTEND_PORT"
echo "Web page: http://$API_HOST:$FRONTEND_PORT/index.html"

cd "$FRONTEND_DIR"
exec env PYTHONPATH="$PROJECT_ROOT" python "$FRONTEND_SERVER" --host 0.0.0.0 --port "$FRONTEND_PORT"
