#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

choose_python() {
  local candidate
  for candidate in python3.12 python3.11 python3.10 python3; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PYTHON_BIN="$(choose_python)"; then
  if command -v brew >/dev/null 2>&1; then
    echo "Python 3.10+ not found. Installing python@3.11 via Homebrew..."
    brew install python@3.11
    if command -v python3.11 >/dev/null 2>&1; then
      PYTHON_BIN="python3.11"
    fi
  fi
fi

if [ -z "${PYTHON_BIN:-}" ]; then
  echo "Python 3.10+ is required."
  echo "Install one first (macOS example): brew install python@3.11"
  exit 1
fi

echo "Using ${PYTHON_BIN}: $($PYTHON_BIN -V 2>&1)"
"$PYTHON_BIN" scripts/bootstrap.py

echo "Environment ready. Activate with: source .venv/bin/activate"
