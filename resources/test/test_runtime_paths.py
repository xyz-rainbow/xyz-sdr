"""Tests de core/runtime_paths.py."""

from __future__ import annotations

import os
from pathlib import Path

from core.runtime_paths import (
    bootstrap_project_caches,
    configure_pycache_prefix,
    get_tests_cache_dir,
    install_venv_pycache_hook,
    pycache_dir,
    pytest_basetemp_dir,
    remove_stray_project_caches,
)


def test_bootstrap_project_caches(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PYTHONPYCACHEPREFIX", raising=False)
    pycache, pytest_cache, basetemp = bootstrap_project_caches(tmp_path)
    assert pycache == tmp_path / "var" / "pycache"
    assert pytest_cache == tmp_path / "var" / "pytest_cache"
    assert basetemp == tmp_path / "var" / "pytest-tmp"
    for directory in (pycache, pytest_cache, basetemp):
        assert directory.is_dir()


def test_remove_stray_project_caches(tmp_path: Path):
    stray_pytest = tmp_path / ".pytest_cache"
    stray_pycache = tmp_path / "__pycache__"
    stray_pytest.mkdir()
    stray_pycache.mkdir()
    removed = remove_stray_project_caches(tmp_path)
    assert stray_pytest in removed
    assert stray_pycache in removed
    assert not stray_pytest.exists()
    assert not stray_pycache.exists()


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
