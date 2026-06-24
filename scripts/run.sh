#!/usr/bin/env bash
# xyz-sdr — run app (requires .venv)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYCACHE="$ROOT/var/pycache"
mkdir -p "$PYCACHE"
export PYTHONPYCACHEPREFIX="$PYCACHE"
export PYTHONUTF8=1
VENV_PY="$ROOT/.venv/bin/python"
MAIN="$ROOT/main.py"
if [[ ! -x "$VENV_PY" ]]; then
  echo "[XX] .venv not found. Run setup/install_drivers first." >&2
  exit 1
fi
exec "$VENV_PY" "$MAIN" "$@"
