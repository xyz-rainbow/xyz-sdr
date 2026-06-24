"""Verifica que cachés de Python/pytest no aparezcan fuera de var/."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".venv", "var", ".git"}


def _is_under_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)


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
