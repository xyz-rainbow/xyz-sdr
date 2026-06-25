"""Bootstrap de cachés en var/ antes de pytest (config en pyproject.toml)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_paths import bootstrap_project_caches, remove_stray_project_caches

bootstrap_project_caches(ROOT)
remove_stray_project_caches(ROOT)
