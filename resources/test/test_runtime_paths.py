"""Tests de core/runtime_paths.py."""

from __future__ import annotations

import os
from pathlib import Path

from core.runtime_paths import (
    configure_pycache_prefix,
    get_tests_cache_dir,
    install_venv_pycache_hook,
    pycache_dir,
)


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


def test_get_tests_cache_dir_default():
    root = get_tests_cache_dir()
    assert root.name == "pytest_cache"
    assert root.parent.name == "var"


def test_install_venv_pycache_hook(tmp_path: Path, monkeypatch):
    import sys

    monkeypatch.delenv("PYTHONPYCACHEPREFIX", raising=False)
    venv_bin = tmp_path / ("Scripts" if sys.platform == "win32" else "bin")
    venv_bin.mkdir(parents=True)
    fake_py = venv_bin / ("python.exe" if sys.platform == "win32" else "python")
    fake_py.write_text("", encoding="utf-8")

    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()

    def fake_run(cmd, **kwargs):
        assert cmd[0] == str(fake_py)
        class Result:
            stdout = str(site_packages)

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)
    pth = install_venv_pycache_hook(tmp_path, fake_py)
    assert pth is not None
    assert pth.is_file()
    assert "PYTHONPYCACHEPREFIX" in pth.read_text(encoding="utf-8")
