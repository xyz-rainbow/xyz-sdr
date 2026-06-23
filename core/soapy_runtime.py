"""
xyz-sdr | core/soapy_runtime.py
Bootstrap de SoapySDR en Windows (PATH, DLL, bindings Python) y diagnóstico.
"""

from __future__ import annotations

import logging
import os
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

POTHOS_CANDIDATES = (
    r"C:\Program Files\PothosSDR",
    r"C:\Program Files (x86)\PothosSDR",
)


@dataclass
class SoapyStatus:
    """Resultado del bootstrap y sondeo de SoapySDR."""

    import_ok: bool = False
    devices: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
    pothos_root: str | None = None
    pothos_bin: str | None = None
    python_bindings_path: str | None = None
    sdrplay_api_ok: bool = False
    sdrplay_plugin_ok: bool = False

    @property
    def has_devices(self) -> bool:
        return bool(self.devices)


_bootstrap_done = False
_last_status: SoapyStatus | None = None


def find_pothos_install() -> str | None:
    """Devuelve la ruta de instalación de PothosSDR si existe."""
    for root in POTHOS_CANDIDATES:
        bin_dir = os.path.join(root, "bin")
        if os.path.isdir(bin_dir):
            return root
    return None


def get_pothos_site_packages(pothos_root: str | None = None) -> str | None:
    """Site-packages de Pothos solo si coincide la versión de Python activa."""
    root = pothos_root or find_pothos_install()
    if not root:
        return None
    return _python_site_packages(root)


def get_pothos_site_packages_for_env(pothos_root: str | None = None) -> str | None:
    """Igual que get_pothos_site_packages — para registrar en PYTHONPATH del usuario."""
    return get_pothos_site_packages(pothos_root)


def _python_site_packages(pothos_root: str) -> str | None:
    ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    path = os.path.join(pothos_root, "lib", ver, "site-packages")
    if os.path.isdir(path):
        return path
    return None


def _fallback_pothos_site_packages(pothos_root: str) -> str | None:
    """Bindings embebidos de otra versión (referencia diagnóstica; no importar)."""
    versions = list_pothos_python_versions(pothos_root)
    if not versions:
        return None
    major, minor = versions[0]
    path = os.path.join(pothos_root, "lib", f"python{major}.{minor}", "site-packages")
    return path if os.path.isdir(path) else None


def list_pothos_python_versions(pothos_root: str | None = None) -> list[tuple[int, int]]:
    """Versiones de Python con bindings SoapySDR incluidos en PothosSDR."""
    root = pothos_root or find_pothos_install()
    if not root:
        return []
    lib_root = os.path.join(root, "lib")
    if not os.path.isdir(lib_root):
        return []
    versions: list[tuple[int, int]] = []
    for name in os.listdir(lib_root):
        if not name.startswith("python"):
            continue
        parts = name.replace("python", "").split(".", 1)
        if len(parts) != 2:
            continue
        try:
            major, minor = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        site_packages = os.path.join(lib_root, name, "site-packages")
        if os.path.isdir(site_packages):
            versions.append((major, minor))
    return sorted(versions, reverse=True)


def get_pothos_site_packages_for_version(major: int, minor: int, pothos_root: str | None = None) -> str | None:
    root = pothos_root or find_pothos_install()
    if not root:
        return None
    path = os.path.join(root, "lib", f"python{major}.{minor}", "site-packages")
    return path if os.path.isdir(path) else None


def _prepend_path(path: str) -> None:
    if not path or not os.path.isdir(path):
        return
    norm = os.path.normcase(os.path.normpath(path))
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if not any(os.path.normcase(os.path.normpath(p)) == norm for p in parts if p):
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")


def _register_dll_directory(path: str) -> None:
    if os.name != "nt" or not path or not os.path.isdir(path):
        return
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(path)
        except Exception as exc:
            logger.debug("add_dll_directory(%s): %s", path, exc)


def _prepend_sys_path(path: str) -> None:
    if path and os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


def check_sdrplay_api() -> bool:
    """Comprueba SDRplay API v3 (carpeta, DLL o servicio)."""
    for root in (r"C:\Program Files\SDRplay", r"C:\Program Files (x86)\SDRplay"):
        if os.path.isdir(root):
            return True
    if os.path.isfile(r"C:\Windows\System32\sdrplay_api.dll"):
        return True
    if os.name == "nt":
        try:
            res = subprocess.run(
                ["sc", "query", "sdrplay-api"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if "RUNNING" in res.stdout or "STOPPED" in res.stdout:
                return True
        except Exception:
            pass
    return False


def check_sdrplay_plugin(timeout: float = 10.0) -> bool:
    """True si SoapySDRUtil encuentra el driver sdrplay."""
    try:
        res = subprocess.run(
            ["SoapySDRUtil", "--find=driver=sdrplay"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        out = (res.stdout or "") + (res.stderr or "")
        return "driver=sdrplay" in out.lower() or "sdrplay" in out.lower()
    except Exception:
        return False


def is_python_64bit() -> bool:
    return struct.calcsize("P") * 8 == 64


def bootstrap_soapy(*, force: bool = False) -> SoapyStatus:
    """
    Prepara PATH/DLL/bindings e intenta importar SoapySDR.

    Idempotente: la segunda llamada devuelve el resultado cacheado salvo force=True.
    """
    global _bootstrap_done, _last_status

    if _bootstrap_done and not force and _last_status is not None:
        return _last_status

    status = SoapyStatus(sdrplay_api_ok=check_sdrplay_api())

    pothos_root = find_pothos_install()
    if pothos_root:
        status.pothos_root = pothos_root
        bin_dir = os.path.join(pothos_root, "bin")
        status.pothos_bin = bin_dir
        _prepend_path(bin_dir)
        _register_dll_directory(bin_dir)

        site_packages = _python_site_packages(pothos_root)
        if site_packages:
            status.python_bindings_path = site_packages
            _prepend_sys_path(site_packages)
        else:
            embedded = _fallback_pothos_site_packages(pothos_root)
            if embedded:
                status.python_bindings_path = embedded
                logger.debug(
                    "Pothos bindings en %s (Python distinto); usar pip SoapySDR.",
                    embedded,
                )

    try:
        import SoapySDR  # noqa: WPS433

        status.import_ok = True
        try:
            status.devices = [dict(d) for d in SoapySDR.Device.enumerate()]
        except Exception as exc:
            status.error = f"enumerate: {exc}"
        status.sdrplay_plugin_ok = check_sdrplay_plugin()
    except ImportError as exc:
        status.import_ok = False
        status.error = str(exc)
        if pothos_root and not status.python_bindings_path:
            status.error = (
                f"{exc} — no hay bindings Pothos para Python "
                f"{sys.version_info.major}.{sys.version_info.minor}. "
                "Ejecuta: pip install SoapySDR"
            )
        elif pothos_root and _python_site_packages(pothos_root) is None:
            embedded = _fallback_pothos_site_packages(pothos_root)
            status.error = (
                f"{exc} — Pothos incluye bindings para otra versión ({embedded}). "
                f"Con Python {sys.version_info.major}.{sys.version_info.minor} usa: pip install SoapySDR"
            )
    except Exception as exc:
        status.import_ok = False
        status.error = str(exc)

    _bootstrap_done = True
    _last_status = status
    return status


def _soapy_pip_supported() -> bool:
    """Wheels pip de SoapySDR suelen existir hasta ~3.12; Pothos embebido es 3.9."""
    return sys.version_info < (3, 13)


def format_hardware_help(status: SoapyStatus) -> str:
    """Texto de ayuda según el fallo detectado."""
    lines: list[str] = []

    if not status.import_ok:
        lines.append("SoapySDR no carga en Python.")
        if status.pothos_root:
            lines.append(f"  PothosSDR detectado en: {status.pothos_root}")
            if status.pothos_bin:
                lines.append(f"  bin: {status.pothos_bin}")
            if status.python_bindings_path:
                lines.append(f"  bindings: {status.python_bindings_path}")
            else:
                lines.append(
                    f"  Sin bindings para Python {sys.version_info.major}.{sys.version_info.minor}."
                )
        else:
            lines.append("  PothosSDR no encontrado. Ejecuta setup\\install_drivers.bat → opción [2].")
        if not is_python_64bit():
            lines.append("  Usa Python 64-bit (amd64).")
        if not _soapy_pip_supported():
            lines.append(
                f"  Python {sys.version_info.major}.{sys.version_info.minor} no tiene wheel SoapySDR en pip."
            )
            lines.append("  Usa Python 3.11 o 3.12 (recomendado) o 3.9 con bindings Pothos embebidos.")
        else:
            lines.append("  Pasos: pip install -r requirements.txt")
        lines.append("         python setup/check_env.py")
        lines.append("         Cierra y reabre la terminal tras instalar drivers.")
        if status.error:
            lines.append(f"  Detalle: {status.error}")
        return "\n".join(lines)

    if not status.has_devices:
        lines.append("SoapySDR importa OK pero no hay dispositivos enumerados.")
        if not status.sdrplay_api_ok:
            lines.append("  SDRplay API no detectada. Instala opción [1] en install_drivers.")
        if not status.sdrplay_plugin_ok:
            lines.append("  Plugin sdrplay no visible. Prueba: SoapySDRUtil --find=driver=sdrplay")
        lines.append("  Comprueba USB, cierra SDRuno/SDRUno y reinicia el servicio SDRplay.")
        return "\n".join(lines)

    return ""


def get_soapy_module() -> Any:
    """Importa SoapySDR tras bootstrap; lanza ImportError si falla."""
    status = bootstrap_soapy()
    if not status.import_ok:
        raise ImportError(status.error or "SoapySDR no disponible")
    import SoapySDR  # noqa: WPS433

    return SoapySDR
