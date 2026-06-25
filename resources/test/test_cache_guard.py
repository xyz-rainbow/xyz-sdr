"""Verifica que cachés de Python/pytest no aparezcan fuera de var/."""

from __future__ import annotations

from pathlib import Path

from core.runtime_paths import (
    PYTEST_BASETEMP_REL,
    PYTEST_CACHE_REL,
    get_tests_cache_dir,
    pycache_dir,
    project_root,
    pytest_basetemp_dir,
)

ROOT = project_root()
SKIP_DIRS = {".venv", "var", ".git"}


def _is_under_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)


def test_pyproject_pytest_cache_dirs():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'cache_dir = "{PYTEST_CACHE_REL}"' in text
    assert f"--basetemp={PYTEST_BASETEMP_REL}" in text
    assert not (ROOT / "pytest.ini").exists()


def test_runtime_paths_match_pyproject():
    assert get_tests_cache_dir() == ROOT / "var" / "pytest_cache"
    assert pytest_basetemp_dir() == ROOT / "var" / "pytest-tmp"
    assert pycache_dir() == ROOT / "var" / "pycache"


def test_no_stray_pytest_cache_in_project():
    offenders = [
        p
        for p in ROOT.rglob(".pytest_cache")
        if p.is_dir() and not _is_under_skipped(p)
    ]
    assert offenders == [], f"Stray .pytest_cache: {offenders}"


def test_no_stray_pycache_in_project():
    offenders = [
        p
        for p in ROOT.rglob("__pycache__")
        if p.is_dir() and not _is_under_skipped(p)
    ]
    assert offenders == [], f"Stray __pycache__: {offenders}"
