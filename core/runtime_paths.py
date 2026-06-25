"""Rutas de runtime compartidas (cachés en var/)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Subdirectorios bajo var/ (única fuente de verdad; pytest lee cache_dir en pyproject.toml).
VAR_DIR_NAME = "var"
PYCACHE_DIR_NAME = "pycache"
PYTEST_CACHE_DIR_NAME = "pytest_cache"
PYTEST_BASETEMP_DIR_NAME = "pytest-tmp"
PYTEST_CACHE_REL = f"{VAR_DIR_NAME}/{PYTEST_CACHE_DIR_NAME}"
PYTEST_BASETEMP_REL = f"{VAR_DIR_NAME}/{PYTEST_BASETEMP_DIR_NAME}"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def var_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / VAR_DIR_NAME


def pycache_dir(root: Path | None = None) -> Path:
    return var_dir(root) / PYCACHE_DIR_NAME


def get_tests_cache_dir(root: Path | None = None) -> Path:
    return var_dir(root) / PYTEST_CACHE_DIR_NAME


def pytest_basetemp_dir(root: Path | None = None) -> Path:
    return var_dir(root) / PYTEST_BASETEMP_DIR_NAME


def configure_pycache_prefix(root: Path | None = None) -> Path:
    """Redirige bytecode (.pyc) a var/pycache en lugar de __pycache__ junto al código."""
    existing = os.environ.get("PYTHONPYCACHEPREFIX")
    if existing:
        if not getattr(sys, "pycache_prefix", None):
            sys.pycache_prefix = existing
        return Path(existing)
    cache = pycache_dir(root)
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["PYTHONPYCACHEPREFIX"] = str(cache)
    sys.pycache_prefix = str(cache)
    return cache


def bootstrap_project_caches(root: Path | None = None) -> tuple[Path, Path, Path]:
    """
    Crea var/pycache, var/pytest_cache y var/pytest-tmp; fija PYTHONPYCACHEPREFIX.

    Debe llamarse lo antes posible (main.py, conftest.py, scripts de test).
    """
    root = (root or project_root()).resolve()
    pycache = configure_pycache_prefix(root)
    pytest_cache = get_tests_cache_dir(root)
    basetemp = pytest_basetemp_dir(root)
    for directory in (var_dir(root), pytest_cache, basetemp):
        directory.mkdir(parents=True, exist_ok=True)
    return pycache, pytest_cache, basetemp


def remove_stray_project_caches(root: Path | None = None) -> list[Path]:
    """Elimina __pycache__ / .pytest_cache en la raíz del repo (legado)."""
    root = (root or project_root()).resolve()
    removed: list[Path] = []
    for name in ("__pycache__", ".pytest_cache"):
        path = root / name
        if path.exists():
            import shutil

            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
    return removed


def install_venv_pycache_hook(
    root: Path | None = None,
    venv_python: Path | str | None = None,
) -> Path | None:
    """Instala un .pth en el venv para fijar PYTHONPYCACHEPREFIX al arrancar Python."""
    import subprocess

    root = (root or project_root()).resolve()
    configure_pycache_prefix(root)

    if venv_python is None:
        candidate = root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
            "python.exe" if os.name == "nt" else "python"
        )
        if not candidate.is_file():
            return None
        venv_python = candidate

    proc = subprocess.run(
        [str(venv_python), "-c", "import site; print(site.getsitepackages()[0])"],
        capture_output=True,
        text=True,
        check=True,
    )
    site_packages = Path(proc.stdout.strip())
    pth_file = site_packages / "xyz-sdr-pycache.pth"
    pth_file.write_text(
        "import os, pathlib; "
        f"_r = pathlib.Path({str(root)!r}); "
        "_c = _r / 'var' / 'pycache'; "
        "_c.mkdir(parents=True, exist_ok=True); "
        "os.environ.setdefault('PYTHONPYCACHEPREFIX', str(_c))\n",
        encoding="utf-8",
    )
    return pth_file
