#!/usr/bin/env bash
# xyz-sdr — run tests (pytest config in pyproject.toml)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "[XX] .venv not found. Run setup/install_drivers first." >&2
  exit 1
fi

# Limpieza de __pycache__ huérfano fuera de var/pycache
# (solo dentro del repo, no recursivo en .venv para mantenerlo rápido)
find "$ROOT" \
  -path "$ROOT/.venv" -prune -o \
  -path "$ROOT/var" -prune -o \
  -path "$ROOT/.git" -prune -o \
  -type d -name "__pycache__" -print -exec rm -rf {} + 2>/dev/null || true

"$VENV_PY" -c "
import sys
from pathlib import Path
ROOT = Path('${ROOT}')
sys.path.insert(0, str(ROOT))
from core.runtime_paths import bootstrap_project_caches, install_venv_pycache_hook, remove_stray_project_caches
bootstrap_project_caches(ROOT)
remove_stray_project_caches(ROOT)
install_venv_pycache_hook(ROOT)
"
exec "$VENV_PY" -m pytest "$ROOT" -m "not slow" "$@"