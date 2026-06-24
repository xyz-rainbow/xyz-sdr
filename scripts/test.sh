#!/usr/bin/env bash
# xyz-sdr — run tests (pytest.ini at repo root)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/var/pycache" "$ROOT/var/pytest_cache" "$ROOT/var/pytest-tmp"
export PYTHONPYCACHEPREFIX="$ROOT/var/pycache"
VENV_PY="$ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "[XX] .venv not found. Run setup/install_drivers first." >&2
  exit 1
fi
"$VENV_PY" -c "from core.runtime_paths import install_venv_pycache_hook; install_venv_pycache_hook()"
exec "$VENV_PY" -m pytest "$ROOT" -m "not slow" "$@"
