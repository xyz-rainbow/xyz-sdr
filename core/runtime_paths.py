"""Rutas de runtime compartidas (cachés en var/)."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def pycache_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "var" / "pycache"


def configure_pycache_prefix(root: Path | None = None) -> Path:
    """Redirige bytecode (.pyc) a var/pycache en lugar de __pycache__ junto al código."""
    existing = os.environ.get("PYTHONPYCACHEPREFIX")
    if existing:
        return Path(existing)
    cache = pycache_dir(root)
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["PYTHONPYCACHEPREFIX"] = str(cache)
    return cache
