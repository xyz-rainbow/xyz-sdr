"""Tests de core/runtime_paths.py."""

from __future__ import annotations

import os
from pathlib import Path

from core.runtime_paths import configure_pycache_prefix, pycache_dir


def test_configure_pycache_prefix(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PYTHONPYCACHEPREFIX", raising=False)
    cache = configure_pycache_prefix(tmp_path)
    assert cache == tmp_path / "var" / "pycache"
    assert cache.is_dir()
    assert os.environ["PYTHONPYCACHEPREFIX"] == str(cache)


def test_pycache_dir_default():
    root = pycache_dir()
    assert root.name == "pycache"
    assert root.parent.name == "var"
