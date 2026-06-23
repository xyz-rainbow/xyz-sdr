"""
xyz-sdr | core/uv_runtime.py
Instalación y uso de uv como gestor de paquetes preferido.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _uv_on_path() -> str | None:
    found = shutil.which("uv")
    return found if found else None


def _uv_via_python(python_exe: str) -> list[str] | None:
    try:
        res = subprocess.run(
            [python_exe, "-m", "uv", "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if res.returncode == 0:
            return [python_exe, "-m", "uv"]
    except Exception:
        pass
    return None


def uv_available(python_exe: str | None = None) -> bool:
    """True si uv está en PATH o como módulo del intérprete indicado."""
    if _uv_on_path():
        return True
    return _uv_via_python(python_exe or sys.executable) is not None


def resolve_uv_command(python_exe: str | None = None) -> list[str]:
    """
    Devuelve el prefijo de comando para invocar uv.

    Preferencia: binario en PATH → python -m uv del intérprete dado.
    """
    python_exe = python_exe or sys.executable
    on_path = _uv_on_path()
    if on_path:
        return [on_path]
    via_py = _uv_via_python(python_exe)
    if via_py:
        return via_py
    scripts_uv = Path(python_exe).resolve().parent / ("uv.exe" if sys.platform == "win32" else "uv")
    if scripts_uv.is_file():
        return [str(scripts_uv)]
    raise FileNotFoundError("uv no encontrado")


def ensure_uv(python_exe: str | None = None) -> list[str]:
    """
    Garantiza que uv esté disponible; lo instala con pip si hace falta.

    Devuelve el prefijo de comando listo para subprocess (p. ej. ['uv'] o [py, '-m', 'uv']).
    """
    python_exe = python_exe or sys.executable
    if uv_available(python_exe):
        return resolve_uv_command(python_exe)

    subprocess.run(
        [python_exe, "-m", "pip", "install", "uv"],
        check=True,
        timeout=300,
    )
    return resolve_uv_command(python_exe)


def uv_pip_install(
    requirements: Path | str,
    *,
    python_exe: str | None = None,
    system: bool = False,
    cwd: Path | str | None = None,
    uv_python: str | None = None,
) -> None:
    """Instala requirements.txt con uv pip."""
    req = Path(requirements)
    bootstrap_py = uv_python or python_exe or sys.executable
    uv_cmd = ensure_uv(bootstrap_py)

    cmd = [*uv_cmd, "pip", "install", "-r", str(req)]
    if uv_python:
        cmd.extend(["--python", uv_python])
    elif python_exe and not system:
        cmd.extend(["--python", python_exe])
    elif system:
        cmd.append("--system")

    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None, timeout=600)


def uv_create_venv(
    venv_dir: Path | str,
    *,
    base_python: str,
    installer_python: str | None = None,
) -> Path:
    """Crea un venv con uv venv --python."""
    venv_path = Path(venv_dir)
    uv_cmd = ensure_uv(installer_python or sys.executable)
    subprocess.run(
        [*uv_cmd, "venv", "--seed", str(venv_path), "--python", base_python],
        check=True,
        timeout=120,
    )
    if sys.platform == "win32":
        py = venv_path / "Scripts" / "python.exe"
    else:
        py = venv_path / "bin" / "python"
    if not py.is_file():
        raise RuntimeError(f"No se creó el venv en {venv_path}")
    return py
