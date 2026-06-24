"""Bootstrap de cachés en var/ antes de importar módulos del proyecto."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_pycache = ROOT / "var" / "pycache"
_pytest_cache = ROOT / "var" / "pytest_cache"
for _dir in (_pycache, _pytest_cache):
    _dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(_pycache))
sys.pycache_prefix = str(_pycache)
