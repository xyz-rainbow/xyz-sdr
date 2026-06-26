"""
tasks.py — tasks de desarrollo para invoke (alternativa a Makefile).

Uso:
    pip install invoke
    invoke --list
    invoke test
    invoke lint
    invoke coverage
    invoke lockfile-regen
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from invoke import task

ROOT = Path(__file__).resolve().parent


def _run(cmd: list[str], **kwargs) -> None:
    """Wrapper para subprocess.run con defaults sensatos."""
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(ROOT), **kwargs)


@task
def test(c, slow=False, cov=True, verbose=False):
    """Correr tests (excluye slow por defecto)."""
    args = ["python", "-m", "pytest", "resources/test/", "-q"]
    if not slow:
        args.append("-m")
        args.append("not slow")
    if cov:
        args.extend([
            "--cov=core",
            "--cov=setup",
            "--cov=tui",
            "--cov-report=term-missing",
            "--cov-fail-under=50",
        ])
    else:
        args.append("--no-cov")
    if verbose:
        args.append("-v")
    _run(args)


@task
def lint(c):
    """Correr ruff check + format check."""
    if not shutil.which("ruff"):
        print("ruff no instalado. pip install ruff==0.6.9")
        return
    _run(["ruff", "check", "."])
    _run(["ruff", "format", "--check", "."])


@task
def format(c):
    """Aplicar ruff format a todo el código."""
    if not shutil.which("ruff"):
        print("ruff no instalado.")
        return
    _run(["ruff", "format", "."])


@task
def coverage(c):
    """Generar reporte HTML de cobertura."""
    _run([
        "python", "-m", "pytest", "resources/test/",
        "--cov=core", "--cov=setup", "--cov=tui",
        "--cov-report=html:htmlcov",
        "--cov-report=term-missing",
        "-m", "not slow",
    ])
    print(f"\nAbrir: {ROOT / 'htmlcov' / 'index.html'}")


@task
def lockfile_regen(c, with_hashes=True):
    """Regenerar requirements.lock y requirements-dev.lock.

    Requiere uv instalado: pip install uv
    """
    if not shutil.which("uv"):
        print("uv no instalado. pip install uv")
        return

    # Crear requisitos runtime sin SoapySDR (no en PyPI)
    tmp_req = ROOT / "var" / "_runtime_no_soapy.txt"
    runtime_req = ROOT / "requirements.txt"
    tmp_req.parent.mkdir(exist_ok=True)
    tmp_req.write_text(
        "\n".join(
            line for line in runtime_req.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("SoapySDR ")
            and "Core SDR" not in line
        ),
        encoding="utf-8",
    )

    # Runtime lockfile
    args_runtime = ["uv", "pip", "compile", str(tmp_req), "-o", str(ROOT / "requirements.lock")]
    if with_hashes:
        args_runtime.append("--generate-hashes")
    _run(args_runtime)

    # Dev lockfile: runtime + dev
    tmp_dev = ROOT / "var" / "_dev_combined.txt"
    tmp_dev.write_text(
        tmp_req.read_text(encoding="utf-8") + "\n\n"
        + (ROOT / "requirements-dev.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    args_dev = ["uv", "pip", "compile", str(tmp_dev), "-o", str(ROOT / "requirements-dev.lock")]
    if with_hashes:
        args_dev.append("--generate-hashes")
    _run(args_dev)

    # Cleanup
    tmp_req.unlink()
    tmp_dev.unlink()
    print(f"\nLockfiles regenerados: requirements.lock, requirements-dev.lock")


@task
def check(c):
    """Alias de scripts/run.ps1 -Check (en PowerShell) o el script equivalente."""
    print("Windows: .\\scripts\\run.ps1 -Check")
    print("Linux:   python setup/check_env.py --verbose")


@task
def sim(c, debug=False):
    """Lanzar app en modo simulación."""
    args = ["python", "main.py", "--sim"]
    if debug:
        args.append("--debug")
    _run(args)


@task
def clean_pycache(c):
    """Limpiar __pycache__ huérfanos fuera de var/ y .venv/."""
    cleaned = 0
    for pycache in ROOT.rglob("__pycache__"):
        if ".venv" in pycache.parts or "var" in pycache.parts or ".git" in pycache.parts:
            continue
        if pycache.is_dir():
            shutil.rmtree(pycache)
            cleaned += 1
    print(f"Limpieza: {cleaned} directorios __pycache__ eliminados")