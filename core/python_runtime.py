"""
xyz-sdr | core/python_runtime.py
Detección de Python compatible con SoapySDR y gestión de venv del proyecto.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.soapy_runtime import (
    find_pothos_install,
    get_pothos_site_packages,
    get_pothos_site_packages_for_version,
    list_pothos_python_versions,
)

# Python 3.9: bindings embebidos en Pothos. 3.10–3.12: wheel pip SoapySDR.
PIP_SOAPY_MIN = (3, 10)
PIP_SOAPY_MAX = (3, 12)
POTHOS_EMBEDDED_PY = (3, 9)

REEXEC_ENV = "XYZ_SDR_REEXEC_DONE"
_PYTHON_VERSION_CACHE: dict[str, tuple[int, int, int] | None] = {}
VENV_DIRNAME = ".venv"
PYTHON312_INSTALLER_URL = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"
WINGET_ALREADY_INSTALLED = {-1978335189, 2316632107}


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


@dataclass(frozen=True)
class ProvisionResult:
    candidate: PythonCandidate | None
    detail: str = ""


def current_version() -> tuple[int, int, int]:
    v = sys.version_info
    return v.major, v.minor, v.micro


def is_python_64bit() -> bool:
    return struct.calcsize("P") * 8 == 64


def _version_in_range(ver: tuple[int, int], low: tuple[int, int], high: tuple[int, int]) -> bool:
    return low <= ver <= high


def is_version_soapy_compatible(ver: tuple[int, int]) -> bool:
    """True si esta versión puede usar SoapySDR (bindings Pothos o pip 3.10–3.12)."""
    if find_pothos_install() and get_pothos_site_packages_for_version(ver[0], ver[1]):
        return True
    return _version_in_range(ver, PIP_SOAPY_MIN, PIP_SOAPY_MAX)


def provision_target_version() -> tuple[int, int]:
    """Versión a instalar cuando no hay Python compatible."""
    pothos_versions = list_pothos_python_versions()
    if pothos_versions:
        return pothos_versions[0]
    return (3, 12)


def provision_prompt_i18n_key() -> str:
    major, minor = provision_target_version()
    if (major, minor) == (3, 9):
        return "py_install_python39_prompt"
    return "py_install_python_prompt"


def provision_running_i18n_key() -> str:
    major, minor = provision_target_version()
    if (major, minor) == (3, 9):
        return "py_install_python39_running"
    return "py_install_python_running"


def provision_fail_i18n_key() -> str:
    major, minor = provision_target_version()
    if (major, minor) == (3, 9):
        return "py_install_python39_fail"
    return "py_install_python_fail"


def provision_manual_i18n_key() -> str:
    major, minor = provision_target_version()
    if (major, minor) == (3, 9):
        return "py_install_python39_manual"
    return "py_install_python_manual"


def is_current_soapy_compatible() -> bool:
    return is_version_soapy_compatible(current_version()[:2])


from core.runtime_paths import project_root


def project_venv_python(root: Path | None = None) -> Path | None:
    root = root or project_root()
    if os.name == "nt":
        candidate = root / VENV_DIRNAME / "Scripts" / "python.exe"
    else:
        candidate = root / VENV_DIRNAME / "bin" / "python"
    return candidate if candidate.is_file() else None


def ensure_project_venv_or_exit() -> Path:
    """Exige .venv del proyecto; sale con mensaje accionable si falta."""
    venv = project_venv_python()
    if venv:
        return venv
    print(
        "Entorno .venv no encontrado.\n"
        "  1. Ejecuta: .\\setup\\install_drivers.ps1 → [1] Instalar o reparar todo\n"
        "  2. Luego:    .\\scripts\\run.ps1\n"
        "Desarrollo (sin .venv): python main.py --allow-system-python"
    )
    sys.exit(1)


def _query_python_version(executable: str) -> tuple[int, int, int] | None:
    norm = os.path.normcase(os.path.abspath(executable))
    cached = _PYTHON_VERSION_CACHE.get(norm)
    if cached is not None:
        return cached
    try:
        res = subprocess.run(
            [executable, "-c", "import sys; print(sys.version_info[0], sys.version_info[1], sys.version_info[2])"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if res.returncode != 0:
            _PYTHON_VERSION_CACHE[norm] = None
            return None
        parts = res.stdout.strip().split()
        if len(parts) != 3:
            _PYTHON_VERSION_CACHE[norm] = None
            return None
        version = int(parts[0]), int(parts[1]), int(parts[2])
        _PYTHON_VERSION_CACHE[norm] = version
        return version
    except Exception:
        _PYTHON_VERSION_CACHE[norm] = None
        return None


def _discover_via_py_launcher() -> list[PythonCandidate]:
    if os.name != "nt":
        return []
    found: list[PythonCandidate] = []
    seen: set[str] = set()

    def add(exe: str, major: int, minor: int, source: str) -> None:
        norm = os.path.normcase(os.path.abspath(exe))
        if norm in seen or not os.path.isfile(exe):
            return
        ver = _query_python_version(exe) or (major, minor, 0)
        seen.add(norm)
        found.append(PythonCandidate(exe, ver, source))

    try:
        res = subprocess.run(
            ["py", "-0p"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        pattern = re.compile(r"^\s*-V:(\d+)\.(\d+)\s+\*\s+(.+)$")
        pattern2 = re.compile(r"^\s*-V:(\d+)\.(\d+)\s+(.+)$")
        for line in (res.stdout or "").splitlines():
            m = pattern.match(line) or pattern2.match(line)
            if not m:
                continue
            add(m.group(3).strip(), int(m.group(1)), int(m.group(2)), "py-launcher")
    except FileNotFoundError:
        pass

    for major, minor in ((3, 12), (3, 11), (3, 10), (3, 9)):
        try:
            res = subprocess.run(
                ["py", f"-{major}.{minor}", "-c", "import sys; print(sys.executable)"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except FileNotFoundError:
            break
        if res.returncode != 0:
            continue
        exe = (res.stdout or "").strip()
        if exe:
            add(exe, major, minor, "py-launcher")

    return found


def _discover_via_windows_registry() -> list[PythonCandidate]:
    if os.name != "nt":
        return []
    import winreg

    found: list[PythonCandidate] = []
    seen: set[str] = set()

    def add(exe: str, ver_hint: str, source: str) -> None:
        norm = os.path.normcase(os.path.abspath(exe))
        if norm in seen or not os.path.isfile(exe):
            return
        ver = _query_python_version(exe)
        if ver is None:
            return
        seen.add(norm)
        found.append(PythonCandidate(exe, ver, source))

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            core = winreg.OpenKey(hive, r"Software\Python\PythonCore")
        except OSError:
            continue
        index = 0
        while True:
            try:
                version_name = winreg.EnumKey(core, index)
                index += 1
            except OSError:
                break
            try:
                ver_key = winreg.OpenKey(core, version_name)
                install_path, _ = winreg.QueryValueEx(ver_key, "InstallPath")
                install_path = str(install_path).rstrip("\\/")
                exe = os.path.join(install_path, "python.exe")
                add(exe, version_name, "registry")
            except OSError:
                continue

    return found


def _discover_windows_install_dirs() -> list[PythonCandidate]:
    if os.name != "nt":
        return []
    found: list[PythonCandidate] = []
    seen: set[str] = set()
    roots: list[Path] = []

    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Programs" / "Python")
    roots.extend(
        [
            Path(r"C:\Program Files"),
            Path(r"C:\Program Files (x86)"),
            Path(r"C:\Python312"),
            Path(r"C:\Python311"),
            Path(r"C:\Python310"),
            Path(r"C:\Python39"),
        ]
    )

    def add(exe: Path, source: str) -> None:
        norm = os.path.normcase(str(exe.resolve()))
        if norm in seen or not exe.is_file():
            return
        ver = _query_python_version(str(exe))
        if ver is None:
            return
        seen.add(norm)
        found.append(PythonCandidate(str(exe), ver, source))

    for root in roots:
        if not root.is_dir():
            continue
        direct = root / "python.exe"
        if direct.is_file() and root.name.lower().startswith("python"):
            add(direct, "windows-path")
            continue
        try:
            for sub in root.iterdir():
                if not sub.is_dir():
                    continue
                name = sub.name.lower()
                if not name.startswith("python"):
                    continue
                py = sub / "python.exe"
                if py.is_file():
                    add(py, "windows-path")
        except OSError:
            continue

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

    for cand in _discover_windows_install_dirs():
        add(cand.executable, cand.source)

    for cand in _discover_via_windows_registry():
        add(cand.executable, cand.source)

    return out


def _soapy_preference_key(cand: PythonCandidate) -> tuple:
    ver = cand.version_short
    pothos_versions = list_pothos_python_versions() if os.name == "nt" else []
    if pothos_versions and ver in pothos_versions:
        embedded_rank = pothos_versions.index(ver)
        return (0, embedded_rank, 0 if cand.source == "venv" else 1, -cand.version[2])

    if ver == (3, 12):
        rank = 1
    elif ver == (3, 11):
        rank = 2
    elif ver == (3, 10):
        rank = 3
    elif ver == POTHOS_EMBEDDED_PY:
        rank = 4
    else:
        rank = 99
    venv_bonus = 0 if cand.source == "venv" else 1
    return (1, rank, venv_bonus, -cand.version[2])


def find_best_soapy_python(root: Path | None = None) -> PythonCandidate | None:
    """Mejor Python instalado compatible con SoapySDR."""
    compatible = [c for c in discover_python_candidates(root) if is_version_soapy_compatible(c.version_short)]
    pothos_versions = list_pothos_python_versions() if os.name == "nt" else []
    if pothos_versions:
        pothos_compatible = [c for c in compatible if c.version_short in pothos_versions]
        if pothos_compatible:
            compatible = pothos_compatible
        else:
            return None
    if not compatible:
        return None
    compatible.sort(key=_soapy_preference_key)
    return compatible[0]


def _winget_executable() -> str | None:
    found = shutil.which("winget")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidate = os.path.join(local, "Microsoft", "WindowsApps", "winget.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def winget_available() -> bool:
    return _winget_executable() is not None


def _refresh_windows_path() -> None:
    if os.name != "nt":
        return
    import winreg

    parts: list[str] = []
    for root, subkey in (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(root, subkey) as key:
                path_val, _ = winreg.QueryValueEx(key, "Path")
                if path_val:
                    parts.append(str(path_val))
        except OSError:
            continue

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        parts.extend(
            [
                os.path.join(local, "Programs", "Python", "Python312"),
                os.path.join(local, "Programs", "Python", "Python312", "Scripts"),
                os.path.join(local, "Programs", "Python", "Python311"),
                os.path.join(local, "Programs", "Python", "Python311", "Scripts"),
                os.path.join(local, "Programs", "Python", "Python39"),
                os.path.join(local, "Programs", "Python", "Python39", "Scripts"),
            ]
        )
    parts.extend(
        [
            r"C:\Python312",
            r"C:\Python312\Scripts",
            r"C:\Python311",
            r"C:\Python311\Scripts",
            r"C:\Python39",
            r"C:\Python39\Scripts",
        ]
    )

    existing = [p for p in os.environ.get("PATH", "").split(";") if p]
    merged: list[str] = []
    seen: set[str] = set()
    for entry in existing + parts:
        if not entry:
            continue
        key = os.path.normcase(entry)
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    if merged:
        os.environ["PATH"] = ";".join(merged)


def _wait_for_compatible_python(*, attempts: int = 15, delay: float = 2.0) -> PythonCandidate | None:
    for _ in range(attempts):
        _refresh_windows_path()
        candidate = find_best_soapy_python()
        if candidate:
            return candidate
        time.sleep(delay)
    return None


def _winget_install_python(package_id: str) -> tuple[bool, str]:
    winget = _winget_executable()
    if not winget:
        return False, "winget no encontrado en PATH"

    cmd = [
        winget,
        "install",
        "-e",
        "--id",
        package_id,
        "--scope",
        "user",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)
    except Exception as exc:
        return False, str(exc)

    output = "\n".join(part for part in (res.stdout, res.stderr) if part).strip()
    if res.returncode == 0 or res.returncode in WINGET_ALREADY_INSTALLED:
        return True, output or "winget OK"
    if "already installed" in output.lower():
        return True, output
    return False, output or f"winget exit code {res.returncode}"


def _winget_install_python312() -> tuple[bool, str]:
    return _winget_install_python("Python.Python.3.12")


def _winget_install_python39() -> tuple[bool, str]:
    return _winget_install_python("Python.Python.3.9")


def _download_python312_installer(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        PYTHON312_INSTALLER_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, timeout=120) as response, open(dest, "wb") as out_file:
        out_file.write(response.read())


def _install_python312_official(installer_path: Path) -> tuple[bool, str]:
    if not installer_path.is_file():
        return False, f"Installer not found: {installer_path}"

    cmd = [
        str(installer_path),
        "/passive",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_launcher=1",
        "Include_pip=1",
        "Include_test=0",
    ]
    try:
        res = subprocess.run(cmd, timeout=900, check=False)
    except Exception as exc:
        return False, str(exc)

    if res.returncode in (0, 3010):
        return True, f"installer exit code {res.returncode}"
    return False, f"installer exit code {res.returncode}"


def provision_compatible_python_verbose(
    *,
    log: Callable[[str], None] | None = None,
    temp_dir: Path | str | None = None,
) -> ProvisionResult:
    """
    Instala Python compatible (3.9 con Pothos o 3.12 vía winget/python.org).
    """
    def say(message: str) -> None:
        if log:
            log(message)

    existing = find_best_soapy_python()
    if existing:
        return ProvisionResult(existing, existing.label())

    if os.name != "nt":
        return ProvisionResult(None, "solo Windows")

    last_detail = ""
    pothos_versions = list_pothos_python_versions()
    if pothos_versions and (3, 9) in pothos_versions:
        if winget_available():
            say("PothosSDR incluye SoapySDR para Python 3.9 — winget install Python.Python.3.9 …")
            ok, detail = _winget_install_python39()
            last_detail = detail
            if ok:
                say("winget terminado; buscando Python 3.9…")
            else:
                say(f"winget falló: {detail[:240]}")
        candidate = _wait_for_compatible_python(attempts=30, delay=2.0)
        if candidate:
            return ProvisionResult(candidate, candidate.label())
        return ProvisionResult(
            None,
            last_detail or "Instala Python 3.9 (64-bit) para usar los bindings SoapySDR de PothosSDR.",
        )

    if winget_available():
        say("winget install Python.Python.3.12 …")
        ok, detail = _winget_install_python312()
        last_detail = detail
        if ok:
            say("winget terminado; buscando Python 3.12…")
        else:
            say(f"winget falló: {detail[:240]}")
    else:
        last_detail = "winget no disponible"
        say("winget no disponible; usando instalador oficial de python.org…")

    candidate = _wait_for_compatible_python(attempts=12, delay=2.0)
    if candidate:
        return ProvisionResult(candidate, candidate.label())

    if winget_available():
        say("Python 3.12 aún no visible; probando instalador oficial de python.org…")

    tmp_root = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())
    installer = tmp_root / "python-3.12.9-amd64.exe"
    try:
        say("Descargando Python 3.12.9 desde python.org…")
        _download_python312_installer(installer)
        say("Ejecutando instalador oficial (acepta el aviso si aparece)…")
        ok, detail = _install_python312_official(installer)
        last_detail = detail
        if not ok:
            return ProvisionResult(None, detail)
    except Exception as exc:
        return ProvisionResult(None, str(exc))

    candidate = _wait_for_compatible_python(attempts=20, delay=2.0)
    if candidate:
        return ProvisionResult(candidate, candidate.label())
    return ProvisionResult(None, last_detail or "Python 3.12 no detectado tras la instalación")


def provision_compatible_python(
    *,
    log: Callable[[str], None] | None = None,
    temp_dir: Path | str | None = None,
) -> PythonCandidate | None:
    return provision_compatible_python_verbose(log=log, temp_dir=temp_dir).candidate


def _use_pothos_soapy_bindings(python_exe: str) -> bool:
    """True si SoapySDR debe venir de Pothos (no pip) para este intérprete."""
    if os.name != "nt" or not find_pothos_install():
        return False
    ver = _query_python_version(python_exe)
    if not ver:
        return False
    return get_pothos_site_packages_for_version(ver[0], ver[1]) is not None


def _venv_site_packages(python_exe: str) -> Path | None:
    try:
        res = subprocess.run(
            [python_exe, "-c", "import site; print(site.getsitepackages()[0])"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return None
        path = Path(res.stdout.strip())
        return path if path.is_dir() else None
    except Exception:
        return None


def configure_venv_pothos_bindings(python_exe: str) -> None:
    """Registra bindings Pothos en el .venv vía .pth."""
    ver = _query_python_version(python_exe)
    if not ver:
        return
    pothos_sp = get_pothos_site_packages_for_version(ver[0], ver[1])
    if not pothos_sp:
        return
    site_dir = _venv_site_packages(python_exe)
    if not site_dir:
        return
    pth = site_dir / "xyz-sdr-pothos.pth"
    pth.write_text(pothos_sp + "\n", encoding="utf-8")


def _ensure_venv_pip(python_exe: str) -> None:
    try:
        res = subprocess.run(
            [python_exe, "-m", "pip", "--version"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if res.returncode == 0:
            return
    except Exception:
        pass
    subprocess.run([python_exe, "-m", "ensurepip", "--upgrade"], check=True, timeout=120)


def _venv_core_libs_missing(python_exe: str) -> bool:
    code = (
        "import importlib.util\n"
        "missing=[m for m in ('numpy','scipy','sounddevice','textual','rich') if importlib.util.find_spec(m) is None]\n"
        "print('1' if missing else '0')"
    )
    try:
        res = subprocess.run(
            [python_exe, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return res.returncode != 0 or res.stdout.strip() != "0"
    except Exception:
        return True


def _remove_project_venv(root: Path) -> None:
    venv_dir = root / VENV_DIRNAME
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)


def _venv_soapy_import_ok(python_exe: str) -> bool:
    from setup.env_state import check_soapy_import

    return check_soapy_import(python_exe)


def _venv_needs_repair(python_exe: str, best: PythonCandidate) -> bool:
    ver = _query_python_version(python_exe)
    if not ver or not is_version_soapy_compatible(ver[:2]):
        return True
    if ver[:2] != best.version_short:
        return True
    if _venv_core_libs_missing(python_exe):
        return True
    if not _venv_soapy_import_ok(python_exe):
        return True
    return False


def _requirements_without_soapy(req_path: Path) -> Path:
    """Genera un requirements temporal sin SoapySDR (p. ej. Python 3.13+ sin wheel)."""
    lines: list[str] = []
    for line in req_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue
        pkg = stripped.split("#", 1)[0].strip()
        if pkg.lower().startswith("soapysdr"):
            continue
        lines.append(line)
    tmp = Path(tempfile.gettempdir()) / "xyz-sdr-requirements-no-soapy.txt"
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp


def find_reexec_target(root: Path | None = None) -> PythonCandidate | None:
    """
    Devuelve el intérprete con el que debe ejecutarse la app.
    Prioridad: .venv del proyecto → Python compatible alternativo.
    """
    if os.environ.get(REEXEC_ENV):
        return None

    root = root or project_root()
    venv_py = project_venv_python(root)
    if venv_py:
        ver = _query_python_version(str(venv_py))
        if ver:
            current = os.path.normcase(os.path.abspath(sys.executable))
            target = os.path.normcase(os.path.abspath(str(venv_py)))
            if current != target:
                return PythonCandidate(str(venv_py), ver, "venv")

    if is_current_soapy_compatible():
        return None

    best = find_best_soapy_python(root)
    if best and os.path.normcase(os.path.abspath(best.executable)) != os.path.normcase(
        os.path.abspath(sys.executable)
    ):
        return best

    return None


def create_project_venv(python_exe: str, root: Path | None = None) -> Path:
    """Crea .venv con uv (preferido) o venv estándar."""
    root = root or project_root()
    venv_dir = root / VENV_DIRNAME
    if venv_dir.exists():
        existing = project_venv_python(root)
        if existing:
            return existing

    try:
        from core.uv_runtime import uv_create_venv

        return uv_create_venv(venv_dir, base_python=python_exe)
    except Exception:
        subprocess.run([python_exe, "-m", "venv", str(venv_dir)], check=True)
        venv_python = project_venv_python(root)
        if not venv_python:
            raise RuntimeError("No se pudo crear .venv")
        _ensure_venv_pip(str(venv_python))
        return venv_python


def install_requirements(
    python_exe: str,
    root: Path | None = None,
    *,
    skip_soapy: bool = False,
) -> None:
    root = root or project_root()
    req = root / "requirements.txt"
    use_pothos = _use_pothos_soapy_bindings(python_exe)
    install_req = _requirements_without_soapy(req) if (skip_soapy or use_pothos) else req
    _ensure_venv_pip(python_exe)
    try:
        from core.uv_runtime import uv_pip_install

        uv_pip_install(install_req, uv_python=str(python_exe), cwd=root)
    except Exception:
        subprocess.run(
            [python_exe, "-m", "pip", "install", "-r", str(install_req)],
            check=True,
            cwd=str(root),
        )
    if use_pothos:
        configure_venv_pothos_bindings(python_exe)
    _write_requirements_marker(root)


def _requirements_marker_path(root: Path) -> Path:
    return root / "var" / "requirements.sha256"


def _requirements_hash(root: Path) -> str:
    import hashlib

    return hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest()


def _requirements_install_needed(root: Path) -> bool:
    marker = _requirements_marker_path(root)
    req = root / "requirements.txt"
    if not req.is_file():
        return False
    digest = _requirements_hash(root)
    return not marker.is_file() or marker.read_text(encoding="utf-8").strip() != digest


def _write_requirements_marker(root: Path) -> None:
    marker = _requirements_marker_path(root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(_requirements_hash(root), encoding="utf-8")


def ensure_project_venv_with_deps(root: Path | None = None) -> Path:
    """
    Crea .venv con el mejor Python compatible e instala requirements.txt.
    Devuelve la ruta al python del venv.
    """
    root = root or project_root()
    best = find_best_soapy_python(root)
    if not best:
        pothos_versions = list_pothos_python_versions()
        hint = ""
        if pothos_versions:
            versions = ", ".join(f"{major}.{minor}" for major, minor in pothos_versions)
            hint = f" PothosSDR incluye bindings para Python {versions}."
        raise RuntimeError(
            "No hay Python compatible con SoapySDR instalado."
            f"{hint} "
            "Instala Python 3.9 (Pothos) o 3.11/3.12 desde python.org o winget."
        )

    existing = project_venv_python(root)
    if existing:
        if _venv_needs_repair(str(existing), best):
            _remove_project_venv(root)
            existing = None

    if existing:
        if _requirements_install_needed(root):
            install_requirements(str(existing), root)
        if not _venv_soapy_import_ok(str(existing)):
            _remove_project_venv(root)
            raise RuntimeError("SoapySDR no importa tras reparar .venv")
        from core.runtime_paths import install_venv_pycache_hook

        install_venv_pycache_hook(root, existing)
        return existing

    venv_python = create_project_venv(best.executable, root)
    created_fresh = True
    try:
        install_requirements(str(venv_python), root)
        if not _venv_soapy_import_ok(str(venv_python)):
            raise RuntimeError("SoapySDR no importa en el nuevo .venv")
    except Exception:
        if created_fresh:
            _remove_project_venv(root)
        raise
    from core.runtime_paths import install_venv_pycache_hook

    install_venv_pycache_hook(root, venv_python)
    return venv_python


def reexec_with_python(executable: str, argv: list[str] | None = None) -> None:
    """Re-lanza el proceso con otro intérprete (una sola vez)."""
    argv = list(argv or sys.argv)
    env = os.environ.copy()
    env[REEXEC_ENV] = "1"
    if argv:
        script = os.path.abspath(argv[0])
        cmd = [executable, script, *argv[1:]]
    else:
        cmd = [executable]
    if os.name == "nt":
        proc = subprocess.run(cmd, env=env)
        sys.exit(proc.returncode)
    os.execve(executable, cmd, env)


def try_reexec_for_soapy() -> bool:
    """
    Re-lanza main.py con el .venv o Python compatible si hace falta.
    Devuelve True si no retorna (re-exec en curso). False si sigue con el intérprete actual.
    """
    if os.environ.get(REEXEC_ENV):
        return False

    target = find_reexec_target()
    if not target:
        return False

    print(
        f"[INFO] Usando entorno del proyecto: {target.label()}…"
        if target.source == "venv"
        else f"[INFO] Python {current_version()[0]}.{current_version()[1]} no es compatible con SoapySDR.\n"
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
