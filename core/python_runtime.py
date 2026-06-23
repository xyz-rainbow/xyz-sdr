"""
xyz-sdr | core/python_runtime.py
Detección de Python compatible con SoapySDR y gestión de venv del proyecto.
"""

from __future__ import annotations

import os
import re
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core.soapy_runtime import find_pothos_install, get_pothos_site_packages

# Python 3.9: bindings embebidos en Pothos. 3.10–3.12: wheel pip SoapySDR.
PIP_SOAPY_MIN = (3, 10)
PIP_SOAPY_MAX = (3, 12)
POTHOS_EMBEDDED_PY = (3, 9)

REEXEC_ENV = "XYZ_SDR_REEXEC_DONE"
VENV_DIRNAME = ".venv"


@dataclass(frozen=True)
class PythonCandidate:
    executable: str
    version: tuple[int, int, int]
    source: str

    @property
    def version_short(self) -> tuple[int, int]:
        return self.version[0], self.version[1]

    def label(self) -> str:
        return f"Python {self.version[0]}.{self.version[1]}.{self.version[2]} ({self.source})"


def current_version() -> tuple[int, int, int]:
    v = sys.version_info
    return v.major, v.minor, v.micro


def is_python_64bit() -> bool:
    return struct.calcsize("P") * 8 == 64


def _version_in_range(ver: tuple[int, int], low: tuple[int, int], high: tuple[int, int]) -> bool:
    return low <= ver <= high


def is_version_soapy_compatible(ver: tuple[int, int]) -> bool:
    """True si esta versión puede usar SoapySDR (Pothos 3.9 o pip 3.10–3.12)."""
    if ver == POTHOS_EMBEDDED_PY:
        root = find_pothos_install()
        return bool(root and get_pothos_site_packages(root))
    return _version_in_range(ver, PIP_SOAPY_MIN, PIP_SOAPY_MAX)


def is_current_soapy_compatible() -> bool:
    return is_version_soapy_compatible(current_version()[:2])


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def project_venv_python(root: Path | None = None) -> Path | None:
    root = root or project_root()
    if os.name == "nt":
        candidate = root / VENV_DIRNAME / "Scripts" / "python.exe"
    else:
        candidate = root / VENV_DIRNAME / "bin" / "python"
    return candidate if candidate.is_file() else None


def _query_python_version(executable: str) -> tuple[int, int, int] | None:
    try:
        res = subprocess.run(
            [executable, "-c", "import sys; print(sys.version_info[0], sys.version_info[1], sys.version_info[2])"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if res.returncode != 0:
            return None
        parts = res.stdout.strip().split()
        if len(parts) != 3:
            return None
        return int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        return None


def _discover_via_py_launcher() -> list[PythonCandidate]:
    if os.name != "nt":
        return []
    try:
        res = subprocess.run(
            ["py", "-0p"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        return []

    found: list[PythonCandidate] = []
    pattern = re.compile(r"^\s*-V:(\d+)\.(\d+)\s+\*\s+(.+)$")
    pattern2 = re.compile(r"^\s*-V:(\d+)\.(\d+)\s+(.+)$")
    for line in (res.stdout or "").splitlines():
        m = pattern.match(line) or pattern2.match(line)
        if not m:
            continue
        major, minor, exe = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        if not exe or not os.path.isfile(exe):
            continue
        ver = _query_python_version(exe) or (major, minor, 0)
        found.append(PythonCandidate(exe, ver, "py-launcher"))
    return found


def discover_python_candidates(root: Path | None = None) -> list[PythonCandidate]:
    """Lista intérpretes candidatos, sin duplicados por ruta."""
    root = root or project_root()
    seen: set[str] = set()
    out: list[PythonCandidate] = []

    def add(exe: str, source: str) -> None:
        norm = os.path.normcase(os.path.abspath(exe))
        if norm in seen or not os.path.isfile(exe):
            return
        ver = _query_python_version(exe)
        if ver is None:
            return
        seen.add(norm)
        out.append(PythonCandidate(exe, ver, source))

    venv_py = project_venv_python(root)
    if venv_py:
        add(str(venv_py), "venv")

    add(sys.executable, "current")

    for cand in _discover_via_py_launcher():
        add(cand.executable, cand.source)

    return out


def _soapy_preference_key(cand: PythonCandidate) -> tuple:
    ver = cand.version_short
    if ver == (3, 12):
        rank = 0
    elif ver == (3, 11):
        rank = 1
    elif ver == (3, 10):
        rank = 2
    elif ver == POTHOS_EMBEDDED_PY:
        rank = 3
    else:
        rank = 99
    venv_bonus = 0 if cand.source == "venv" else 1
    return (rank, venv_bonus, -cand.version[2])


def find_best_soapy_python(root: Path | None = None) -> PythonCandidate | None:
    """Mejor Python instalado compatible con SoapySDR."""
    compatible = [c for c in discover_python_candidates(root) if is_version_soapy_compatible(c.version_short)]
    if not compatible:
        return None
    compatible.sort(key=_soapy_preference_key)
    return compatible[0]


def find_reexec_target(root: Path | None = None) -> PythonCandidate | None:
    """
    Si el Python actual no es compatible, devuelve un sustituto (venv primero, luego py launcher).
    """
    if is_current_soapy_compatible():
        return None
    if os.environ.get(REEXEC_ENV):
        return None

    venv_py = project_venv_python(root)
    if venv_py:
        ver = _query_python_version(str(venv_py))
        if ver and is_version_soapy_compatible(ver[:2]):
            return PythonCandidate(str(venv_py), ver, "venv")

    return find_best_soapy_python(root)


def create_project_venv(python_exe: str, root: Path | None = None) -> Path:
    """Crea .venv con el intérprete indicado."""
    root = root or project_root()
    venv_dir = root / VENV_DIRNAME
    if venv_dir.exists():
        return project_venv_python(root) or venv_dir / "Scripts" / "python.exe"

    subprocess.run([python_exe, "-m", "venv", str(venv_dir)], check=True)
    venv_python = project_venv_python(root)
    if not venv_python:
        raise RuntimeError("No se pudo crear .venv")
    return venv_python


def install_requirements(python_exe: str, root: Path | None = None) -> None:
    root = root or project_root()
    req = root / "requirements.txt"
    subprocess.run(
        [python_exe, "-m", "pip", "install", "-r", str(req)],
        check=True,
        cwd=str(root),
    )


def ensure_project_venv_with_deps(root: Path | None = None) -> Path:
    """
    Crea .venv con el mejor Python compatible e instala requirements.txt.
    Devuelve la ruta al python del venv.
    """
    root = root or project_root()
    existing = project_venv_python(root)
    if existing:
        ver = _query_python_version(str(existing))
        if ver and is_version_soapy_compatible(ver[:2]):
            install_requirements(str(existing), root)
            return existing

    best = find_best_soapy_python(root)
    if not best:
        raise RuntimeError(
            "No hay Python 3.9 (Pothos) ni 3.10–3.12 instalado. "
            "Instala Python 3.12 desde python.org o con: winget install Python.Python.3.12"
        )

    venv_python = create_project_venv(best.executable, root)
    install_requirements(str(venv_python), root)
    return venv_python


def reexec_with_python(executable: str, argv: list[str] | None = None) -> None:
    """Re-lanza el proceso con otro intérprete (una sola vez)."""
    argv = argv or sys.argv
    env = os.environ.copy()
    env[REEXEC_ENV] = "1"
    cmd = [executable, *argv[1:]]
    if os.name == "nt":
        proc = subprocess.run(cmd, env=env)
        sys.exit(proc.returncode)
    os.execve(executable, cmd, env)


def try_reexec_for_soapy(*, force_sim: bool = False) -> bool:
    """
    Re-lanza main.py con Python compatible si hace falta.
    Devuelve True si no retorna (re-exec en curso). False si sigue con el intérprete actual.
    """
    if force_sim or os.environ.get(REEXEC_ENV):
        return False

    target = find_reexec_target()
    if not target:
        return False

    if os.path.normcase(os.path.abspath(target.executable)) == os.path.normcase(os.path.abspath(sys.executable)):
        return False

    print(
        f"[INFO] Python {current_version()[0]}.{current_version()[1]} no es compatible con SoapySDR.\n"
        f"       Re-lanzando con {target.label()}…"
    )
    reexec_with_python(target.executable)
    return True  # unreachable


def format_python_compat_status(lang: str = "es") -> tuple[str, str]:
    """Etiqueta corta para el instalador: (texto, color_key ok|warn|fail)."""
    ver = current_version()
    vshort = ver[:2]
    if is_current_soapy_compatible():
        return (f"Python {ver[0]}.{ver[1]}.{ver[2]} — OK SoapySDR", "ok")
    best = find_best_soapy_python()
    if best:
        if lang == "es":
            return (
                f"Python {ver[0]}.{ver[1]} — incompatible; disponible {best.version[0]}.{best.version[1]}",
                "warn",
            )
        return (
            f"Python {ver[0]}.{ver[1]} — incompatible; available {best.version[0]}.{best.version[1]}",
            "warn",
        )
    if lang == "es":
        return (f"Python {ver[0]}.{ver[1]} — incompatible; instala 3.11/3.12", "fail")
    return (f"Python {ver[0]}.{ver[1]} — incompatible; install 3.11/3.12", "fail")
