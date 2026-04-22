#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_CONFIG="$VENV_DIR/pyvenv.cfg"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

if [[ ! -f "$PROJECT_ROOT/pyproject.toml" ]]; then
  echo "pyproject.toml not found in current directory: $PROJECT_ROOT" >&2
  echo "Please run this script from the project root." >&2
  exit 1
fi

if [[ -d "$VENV_DIR" ]] && { [[ -f "$VENV_PYTHON" ]] || [[ -f "$VENV_CONFIG" ]]; }; then
  echo "Virtual environment already exists at .venv, skipping setup."
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed or not in PATH." >&2
  exit 1
fi

mkdir -p "$UV_CACHE_DIR"

echo "Creating virtual environment with uv sync..."
UV_CACHE_DIR="$UV_CACHE_DIR" uv sync
echo "Environment setup finished: .venv"
