"""
xyz-sdr | core/soapy_runtime.py
Bootstrap de SoapySDR en Windows (PATH, DLL, bindings Python) y diagnóstico.
"""

from __future__ import annotations

import logging
import os
import re
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

_SDRPLAY_SOAPY_MODULE_HINTS = ("sdrplay", "sdrplay3")
# Pothos 2021.07.25 incluye sdrPlaySupport.dll antiguo (jul 2021); API v3.15+ requiere SoapySDRPlay3.
_LEGACY_SDRPLAY_MODULE_CUTOFF = 1_650_000_000  # ~2022-04-15


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
    sdrplay_api_bin: str | None = None
    sdrplay_plugin_module: str | None = None
    sdrplay_plugin_status: str = "missing"  # missing | legacy | present

    @property
    def has_devices(self) -> bool:
        return bool(self.devices)

    @property
    def sdrplay_plugin_module_ok(self) -> bool:
        return self.sdrplay_plugin_status == "present"


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


def _preferred_sdrplay_api_subdirs() -> tuple[str, ...]:
    if is_python_64bit():
        return ("x64", "amd64", "win64", "bin", "lib")
    return ("x86", "win32", "bin", "lib")


def _score_sdrplay_api_dir(dirpath: str) -> int:
    lower = dirpath.lower().replace("\\", "/")
    if "arm64" in lower or "aarch64" in lower:
        return -100
    score = 0
    for idx, token in enumerate(_preferred_sdrplay_api_subdirs()):
        if f"/{token}/" in f"{lower}/" or lower.endswith(f"/{token}"):
            score = max(score, 100 - idx)
    return score


def find_sdrplay_api_bin() -> str | None:
    """Directorio con sdrplay_api.dll; en Windows amd64 prioriza API\\x64 sobre arm64."""
    candidates: list[tuple[int, str]] = []
    for root in (r"C:\Program Files\SDRplay", r"C:\Program Files (x86)\SDRplay"):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            if any(name.lower() == "sdrplay_api.dll" for name in files):
                candidates.append((_score_sdrplay_api_dir(dirpath), dirpath))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_path = candidates[0]
        if best_score >= 0:
            return best_path
    if os.path.isfile(r"C:\Windows\System32\sdrplay_api.dll"):
        return r"C:\Windows\System32"
    return None


def find_sdrplay_api_dll() -> str | None:
    api_bin = find_sdrplay_api_bin()
    if not api_bin:
        return None
    path = os.path.join(api_bin, "sdrplay_api.dll")
    return path if os.path.isfile(path) else None


def assess_sdrplay_soapy_module(module_path: str | None) -> str:
    """Clasifica el módulo Soapy sdrplay: missing | legacy | present."""
    if not module_path or not os.path.isfile(module_path):
        return "missing"
    name = os.path.basename(module_path).lower()
    if name == "soapy sdrplay3.dll":
        return "present"
    try:
        if os.path.getmtime(module_path) < _LEGACY_SDRPLAY_MODULE_CUTOFF:
            return "legacy"
    except OSError:
        pass
    return "present"


def sync_sdrplay_api_dll_to_pothos(pothos_root: str | None = None) -> bool:
    """
    Sincroniza sdrplay_api.dll x64 al runtime de Soapy.
    Prioriza bin de Pothos; si no hay permisos, usa %LOCALAPPDATA%\\xyz-sdr\\bin.
    """
    src = find_sdrplay_api_dll()
    if not src:
        return False

    updated = False
    root = pothos_root or find_pothos_install()
    if root:
        dest = os.path.join(root, "bin", "sdrplay_api.dll")
        if _copy_if_newer(src, dest):
            updated = True
        else:
            _disable_stale_pothos_api_dll(dest)

    user_bin = user_xyz_sdr_bin_dir()
    os.makedirs(user_bin, exist_ok=True)
    user_dest = os.path.join(user_bin, "sdrplay_api.dll")
    if _copy_if_newer(src, user_dest):
        updated = True
        _prepend_path(user_bin)
        _register_dll_directory(user_bin)

    plugin_dir = user_soapy_plugin_dir()
    os.makedirs(plugin_dir, exist_ok=True)
    plugin_dest = os.path.join(plugin_dir, "sdrplay_api.dll")
    if _copy_if_newer(src, plugin_dest):
        updated = True
        _register_dll_directory(plugin_dir)

    return updated or os.path.isfile(user_dest)


def _disable_stale_pothos_api_dll(dest: str) -> None:
    """Renombra sdrplay_api.dll antigua en Pothos si no se pudo actualizar."""
    if not os.path.isfile(dest):
        return
    try:
        src = find_sdrplay_api_dll()
        if src and os.path.getsize(dest) == os.path.getsize(src):
            return
    except OSError:
        pass
    disabled = dest + ".pothos-legacy"
    if os.path.isfile(disabled):
        return
    try:
        os.rename(dest, disabled)
        logger.info("Desactivada API legacy en Pothos: %s", disabled)
    except OSError as exc:
        logger.warning("No se pudo renombrar API legacy en Pothos: %s", exc)


def _copy_if_newer(src: str, dest: str) -> bool:
    try:
        src_size = os.path.getsize(src)
        if os.path.isfile(dest) and os.path.getsize(dest) == src_size:
            return True
        import shutil

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        logger.info("Actualizado %s desde %s", dest, src)
        return True
    except OSError as exc:
        logger.warning("No se pudo copiar %s → %s: %s", src, dest, exc)
        return False


def _soapy_modules_dir(pothos_root: str) -> str | None:
    lib_soapy = os.path.join(pothos_root, "lib", "SoapySDR")
    if not os.path.isdir(lib_soapy):
        return None
    candidates: list[str] = []
    for name in os.listdir(lib_soapy):
        if name.startswith("modules"):
            path = os.path.join(lib_soapy, name)
            if os.path.isdir(path):
                candidates.append(path)
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0]


def user_soapy_plugin_dir() -> str:
    """Directorio escribible para el plugin Soapy sdrplay (sin permisos de admin)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    return os.path.join(base, "xyz-sdr", "SoapySDR", "modules0.8")


def user_xyz_sdr_bin_dir() -> str:
    """Bin escribible para DLLs de runtime (p. ej. sdrplay_api.dll)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    return os.path.join(base, "xyz-sdr", "bin")


def soapy_plugin_search_dirs(pothos_root: str | None = None) -> list[str]:
    """Directorios donde buscar módulos Soapy (SOAPY_SDR_PLUGIN_PATH, usuario, Pothos)."""
    from core.driver_runtime import bundled_plugins_dir, legacy_bundled_plugins_dir

    dirs: list[str] = []
    seen: set[str] = set()

    def _add(path: str | None) -> None:
        if not path:
            return
        norm = os.path.normcase(os.path.normpath(path))
        if norm in seen or not os.path.isdir(path):
            return
        seen.add(norm)
        dirs.append(path)

    for part in os.environ.get("SOAPY_SDR_PLUGIN_PATH", "").split(os.pathsep):
        _add(part.strip())

    _add(str(bundled_plugins_dir()))
    _add(str(legacy_bundled_plugins_dir()))
    _add(user_soapy_plugin_dir())

    root = pothos_root or find_pothos_install()
    if root:
        _add(_soapy_modules_dir(root))

    return dirs


def _iter_sdrplay_module_paths(search_dirs: list[str]) -> list[str]:
    paths: list[str] = []
    for mod_dir in search_dirs:
        try:
            names = os.listdir(mod_dir)
        except OSError:
            continue
        for filename in names:
            lower = filename.lower()
            if not lower.endswith(".dll"):
                continue
            if any(hint in lower for hint in _SDRPLAY_SOAPY_MODULE_HINTS):
                paths.append(os.path.join(mod_dir, filename))
    return paths


def find_sdrplay_soapy_module(pothos_root: str | None = None) -> str | None:
    """Ruta al .dll del módulo SoapySDR para SDRplay (prioriza no-legacy)."""
    candidates = _iter_sdrplay_module_paths(soapy_plugin_search_dirs(pothos_root))
    if not candidates:
        return None

    def sort_key(path: str) -> tuple[int, float]:
        state = assess_sdrplay_soapy_module(path)
        rank = 0 if state == "present" else 1 if state == "legacy" else 2
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        return rank, -mtime

    return sorted(candidates, key=sort_key)[0]


def is_sdrplay_soapy_module_ok(pothos_root: str | None = None) -> bool:
    """True si hay un módulo Soapy sdrplay instalado y no es legacy."""
    module = find_sdrplay_soapy_module(pothos_root)
    return assess_sdrplay_soapy_module(module) == "present"


def _configure_soapy_plugin_path(pothos_root: str) -> None:
    from core.driver_runtime import resolve_bundled_sdrplay_plugin

    user_dir = user_soapy_plugin_dir()
    user_module = os.path.join(user_dir, "sdrPlaySupport.dll")
    if os.path.isfile(user_module) and assess_sdrplay_soapy_module(user_module) == "present":
        _prepend_soapy_plugin_dir(user_dir)
        logger.info("SOAPY plugin path: user dir %s", user_dir)
        return

    bundled = resolve_bundled_sdrplay_plugin()
    if bundled is not None and assess_sdrplay_soapy_module(str(bundled)) == "present":
        _prepend_soapy_plugin_dir(str(bundled.parent))
        logger.info("SOAPY plugin path: bundled %s", bundled.parent)
        return

    mod_dir = _soapy_modules_dir(pothos_root)
    if mod_dir:
        has_non_legacy_sdrplay = False
        try:
            for name in os.listdir(mod_dir):
                lower = name.lower()
                if not lower.endswith(".dll"):
                    continue
                if not any(hint in lower for hint in _SDRPLAY_SOAPY_MODULE_HINTS):
                    continue
                full = os.path.join(mod_dir, name)
                if assess_sdrplay_soapy_module(full) != "legacy":
                    has_non_legacy_sdrplay = True
                    break
        except OSError:
            has_non_legacy_sdrplay = True
        if has_non_legacy_sdrplay:
            _prepend_soapy_plugin_dir(mod_dir)
        else:
            logger.warning("Omitiendo directorio Pothos con plugin sdrplay legacy: %s", mod_dir)

    if os.path.isdir(user_dir):
        _prepend_soapy_plugin_dir(user_dir)


def _prepend_soapy_plugin_dir(mod_dir: str) -> None:
    norm_mod = os.path.normcase(os.path.normpath(mod_dir))
    current = os.environ.get("SOAPY_SDR_PLUGIN_PATH", "")
    parts = [part for part in current.split(os.pathsep) if part]
    if any(os.path.normcase(os.path.normpath(part)) == norm_mod for part in parts):
        return
    os.environ["SOAPY_SDR_PLUGIN_PATH"] = mod_dir + (os.pathsep + current if current else "")


def _soapy_util_executable() -> str:
    from core.driver_runtime import bundled_soapy_util

    util = bundled_soapy_util()
    if util is not None:
        return str(util)
    pothos = find_pothos_install()
    if pothos:
        util = os.path.join(pothos, "bin", "SoapySDRUtil.exe")
        if os.path.isfile(util):
            return util
    return "SoapySDRUtil"


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


def _parse_sdrplay_find_stdout(stdout: str) -> bool:
    """True solo si SoapySDRUtil reporta al menos un dispositivo sdrplay en stdout."""
    text = stdout or ""
    lowered = text.lower()
    if "no devices found" in lowered:
        return False
    if "found device" not in lowered:
        return False
    return bool(re.search(r"driver\s*=\s*sdrplay", text, re.IGNORECASE))


def check_sdrplay_service_running() -> bool:
    """True si el servicio Windows SDRplay API está en ejecución."""
    if os.name != "nt":
        return True
    for service_name in ("SDRplayAPIService", "sdrplay-api"):
        try:
            res = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode != 0:
                continue
            return "RUNNING" in (res.stdout or "")
        except Exception:
            continue
    return False


def check_sdrplay_plugin(timeout: float = 10.0) -> bool:
    """True si SoapySDRUtil enumera al menos un dispositivo con driver sdrplay."""
    try:
        res = subprocess.run(
            [_soapy_util_executable(), "--find=driver=sdrplay"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return _parse_sdrplay_find_stdout(res.stdout or "")
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

    from core.driver_runtime import bundled_soapy_dll_dir

    soapy_bundled = bundled_soapy_dll_dir()
    if soapy_bundled is not None:
        soapy_path = str(soapy_bundled)
        _prepend_path(soapy_path)
        _register_dll_directory(soapy_path)
        logger.info("Soapy bundled runtime: %s", soapy_path)

    sync_sdrplay_api_dll_to_pothos()
    user_bin = user_xyz_sdr_bin_dir()
    user_api = os.path.join(user_bin, "sdrplay_api.dll")
    if os.path.isfile(user_api):
        _prepend_path(user_bin)
        _register_dll_directory(user_bin)

    api_bin = find_sdrplay_api_bin()
    if api_bin:
        status.sdrplay_api_bin = api_bin
        _prepend_path(api_bin)
        _register_dll_directory(api_bin)

    pothos_root = find_pothos_install()
    if pothos_root:
        status.pothos_root = pothos_root
        bin_dir = os.path.join(pothos_root, "bin")
        status.pothos_bin = bin_dir
        _prepend_path(bin_dir)
        _register_dll_directory(bin_dir)
        _configure_soapy_plugin_path(pothos_root)
        status.sdrplay_plugin_module = find_sdrplay_soapy_module(pothos_root)
        status.sdrplay_plugin_status = assess_sdrplay_soapy_module(status.sdrplay_plugin_module)
        if not os.path.isfile(user_api):
            sync_sdrplay_api_dll_to_pothos(pothos_root)

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
            if status.sdrplay_plugin_status == "legacy":
                lines.append(
                    "  Módulo Soapy sdrplay de Pothos 2021 (sdrPlaySupport.dll) — incompatible con SDRplay API v3.15+."
                )
                lines.append(
                    "  Instala SoapySDRPlay3: .\\setup\\install_drivers.ps1 → [1] Reparar todo"
                )
            elif status.sdrplay_plugin_module:
                lines.append(
                    f"  Módulo Soapy sdrplay presente ({os.path.basename(status.sdrplay_plugin_module)}) "
                    "pero no enumera RSP."
                )
                lines.append("  ¿RSP conectado por USB? Cierra SDRuno y reinicia SDRplayAPIService.")
            else:
                lines.append(
                    "  Módulo Soapy sdrplay no encontrado en PothosSDR/lib/SoapySDR/modules*."
                )
                lines.append(
                    "  Instala SoapySDRPlay3: .\\setup\\install_drivers.ps1 → [1] Reparar todo"
                )
            lines.append("  Prueba: SoapySDRUtil --find=driver=sdrplay")
            if status.sdrplay_api_bin and "arm64" in status.sdrplay_api_bin.lower():
                lines.append(
                    f"  AVISO: API en ruta arm64 ({status.sdrplay_api_bin}) — debe usarse x64 en Windows amd64."
                )
            if not check_sdrplay_service_running():
                lines.append("  Servicio SDRplayAPIService detenido — Start-Service o Restart-Service.")
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
