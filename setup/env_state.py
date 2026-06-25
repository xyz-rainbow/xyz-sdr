"""
xyz-sdr | setup/env_state.py
Detección unificada del entorno (instalador, check_env, main).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

POTHOS_BIN_TARGETS = (
    r"C:\Program Files\PothosSDR\bin",
    r"C:\Program Files\SoapySDR\bin",
)

CORE_LIBS = ("numpy", "scipy", "sounddevice", "textual", "rich")


@dataclass
class EnvironmentState:
    sdrplay_ok: bool = False
    pothos_installed: bool = False
    path_in_process: bool = False
    path_in_registry: bool = False
    venv_path: Path | None = None
    python_libs_missing: list[str] = field(default_factory=list)
    soapy_import_ok: bool = False
    has_devices: bool = False
    device_count: int = 0
    sdrplay_plugin_ok: bool = False
    blockers: list[str] = field(default_factory=list)

    @property
    def path_ok(self) -> bool:
        return self.path_in_process or self.path_in_registry

    @property
    def path_needs_terminal_restart(self) -> bool:
        return self.path_in_registry and not self.path_in_process

    @property
    def venv_ok(self) -> bool:
        return self.venv_path is not None and self.venv_path.is_file()

    @property
    def python_libs_ok(self) -> bool:
        return self.venv_ok and not self.python_libs_missing

    @property
    def pothos_ready(self) -> bool:
        return self.pothos_installed and self.path_ok

    @property
    def python_env_ready(self) -> bool:
        return self.venv_ok and self.python_libs_ok and self.soapy_import_ok

    @property
    def drivers_ready(self) -> bool:
        return self.sdrplay_ok and self.pothos_ready and self.sdrplay_plugin_ok

    @property
    def env_ready(self) -> bool:
        """Entorno instalado: drivers + .venv + deps + SoapySDR import (sin hardware)."""
        return self.drivers_ready and self.python_env_ready

    @property
    def hardware_ready(self) -> bool:
        return self.env_ready and self.has_devices

    @property
    def sim_ready(self) -> bool:
        return self.env_ready

    @property
    def ready_for_hardware(self) -> bool:
        return self.hardware_ready

    @property
    def install_blockers(self) -> list[str]:
        """Blockers que impiden env_ready (excluye hardware desconectado)."""
        install_keys = {
            "sdrplay_api",
            "pothos",
            "pothos_path",
            "soapy_sdrplay3",
            "venv",
            "python_libs",
            "soapysdr",
        }
        return [b for b in self.blockers if b in install_keys]

    def readiness_level(self) -> str:
        if self.hardware_ready:
            return "hardware"
        if self.env_ready:
            return "env"
        return "pending"


from core.runtime_paths import project_root


def path_contains_pothos(path_str: str) -> bool:
    lower = path_str.lower()
    return any(target.lower() in lower for target in POTHOS_BIN_TARGETS)


def read_path_from_registry() -> str:
    if os.name != "nt":
        return ""
    import winreg

    parts: list[str] = []
    for root, subkey in (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(root, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value:
                    parts.append(str(value))
        except OSError:
            continue
    return ";".join(parts)


def check_core_libs(python_exe: str) -> tuple[list[str], list[str]]:
    code = (
        "import json\n"
        f"libs={list(CORE_LIBS)!r}\n"
        "installed, missing = [], []\n"
        "for lib in libs:\n"
        "    try:\n"
        "        __import__(lib)\n"
        "        installed.append(lib)\n"
        "    except ImportError:\n"
        "        missing.append(lib)\n"
        "print(json.dumps({'installed': installed, 'missing': missing}))"
    )
    try:
        res = subprocess.run(
            [python_exe, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            return data.get("installed", []), data.get("missing", [])
    except Exception:
        pass
    return [], list(CORE_LIBS)


def check_soapy_import(python_exe: str) -> bool:
    try:
        res = subprocess.run(
            [python_exe, "-c", "import SoapySDR"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def probe_soapy_in_python(python_exe: str) -> tuple[bool, list[dict]]:
    """Importa SoapySDR y enumera dispositivos en el intérprete indicado."""
    code = (
        "import json\n"
        "try:\n"
        "    import SoapySDR\n"
        "    devices = [dict(d) for d in SoapySDR.Device.enumerate()]\n"
        "    print(json.dumps({'ok': True, 'devices': devices}))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'ok': False, 'error': str(exc)}))\n"
    )
    try:
        res = subprocess.run(
            [python_exe, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            if data.get("ok"):
                devices = data.get("devices") or []
                return True, devices
    except Exception:
        pass
    return False, []


def _same_python_executable(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def probe_environment(*, bootstrap_soapy: bool = True) -> EnvironmentState:
    from core.python_runtime import project_venv_python
    from core.soapy_runtime import (
        bootstrap_soapy,
        check_sdrplay_api,
        check_sdrplay_plugin,
        find_pothos_install,
        is_sdrplay_soapy_module_ok,
    )

    state = EnvironmentState()
    blockers: list[str] = []

    state.sdrplay_ok = check_sdrplay_api()
    if not state.sdrplay_ok:
        blockers.append("sdrplay_api")

    state.pothos_installed = find_pothos_install() is not None
    if not state.pothos_installed:
        blockers.append("pothos")

    process_path = os.environ.get("PATH", "")
    registry_path = read_path_from_registry()
    state.path_in_process = path_contains_pothos(process_path)
    state.path_in_registry = path_contains_pothos(registry_path)
    if state.pothos_installed and not state.path_ok:
        blockers.append("pothos_path")

    venv_py = project_venv_python(project_root())
    state.venv_path = venv_py
    if not state.venv_ok:
        blockers.append("venv")

    if state.venv_ok:
        _, missing = check_core_libs(str(venv_py))
        state.python_libs_missing = missing
        if missing:
            blockers.append("python_libs")
        state.soapy_import_ok = check_soapy_import(str(venv_py))
        if not state.soapy_import_ok:
            blockers.append("soapysdr")

    if bootstrap_soapy and state.venv_ok:
        venv_str = str(venv_py)
        if _same_python_executable(sys.executable, venv_str):
            status = bootstrap_soapy(force=True)
            state.soapy_import_ok = status.import_ok
            state.has_devices = status.has_devices
            state.device_count = len(status.devices)
            if not status.import_ok and "soapysdr" not in blockers:
                blockers.append("soapysdr")
        elif state.soapy_import_ok:
            ok, devices = probe_soapy_in_python(venv_str)
            if not ok:
                state.soapy_import_ok = False
                if "soapysdr" not in blockers:
                    blockers.append("soapysdr")
            else:
                state.device_count = len(devices)
                state.has_devices = state.device_count > 0

    state.sdrplay_plugin_ok = (
        check_sdrplay_plugin() if state.sdrplay_ok else is_sdrplay_soapy_module_ok()
    )
    if state.sdrplay_ok and state.pothos_installed and not state.sdrplay_plugin_ok:
        blockers.append("soapy_sdrplay3")

    state.blockers = blockers
    return state
