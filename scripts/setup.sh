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
  echo "Python 3.10+ is required."
  echo "Install one first (macOS example): brew install python@3.11"
  exit 1
fi

echo "Using ${PYTHON_BIN}: $($PYTHON_BIN -V 2>&1)"

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade --force-reinstall -r requirements.txt

echo "Environment ready. Activate with: source .venv/bin/activate"
