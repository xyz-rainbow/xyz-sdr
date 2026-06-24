"""Rutas de runtime compartidas (cachés en var/)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def pycache_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "var" / "pycache"


def get_tests_cache_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "var" / "pytest_cache"


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
