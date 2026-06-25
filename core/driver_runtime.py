"""xyz-sdr | core/driver_runtime.py — rutas bundled drivers/win-x64."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from core.runtime_paths import project_root

BUNDLED_PLATFORM = "win-x64"
PLUGIN_DLL_NAME = "sdrPlaySupport.dll"
_MIN_PLUGIN_BYTES = 32_768


def drivers_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "drivers"


def bundled_platform() -> str:
    if os.name == "nt" and sys.maxsize > 2**32:
        return BUNDLED_PLATFORM
    return BUNDLED_PLATFORM


def bundled_win_x64_dir(root: Path | None = None) -> Path:
    return drivers_root(root) / bundled_platform()


def bundled_soapy_dir(root: Path | None = None) -> Path:
    return bundled_win_x64_dir(root) / "soapy"


def bundled_plugins_dir(root: Path | None = None) -> Path:
    return bundled_win_x64_dir(root) / "plugins"


def legacy_bundled_plugins_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "resources" / "bin" / "win-x64"


def bundled_manifest_path(root: Path | None = None) -> Path:
    return bundled_win_x64_dir(root) / "manifest.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_bundled_manifest(root: Path | None = None) -> dict | None:
    """Manifest canónico en drivers/win-x64; fallback a resources/bin/win-x64."""
    manifest = _load_manifest_file(bundled_manifest_path(root))
    if manifest is not None:
        return manifest
    return _load_manifest_file(legacy_bundled_plugins_dir(root) / "manifest.json")


def _validate_plugin_against_manifest(dll: Path, manifest: dict | None) -> bool:
    if manifest is None:
        return True
    try:
        size = dll.stat().st_size
    except OSError:
        return False
    expected_size = manifest.get("size_bytes")
    if isinstance(expected_size, int) and size != expected_size:
        return False
    expected_sha = manifest.get("sha256")
    if isinstance(expected_sha, str) and _sha256_file(dll) != expected_sha.lower():
        return False
    return True


def resolve_bundled_sdrplay_plugin(
    *,
    validate: bool = True,
    root: Path | None = None,
) -> Path | None:
    """Ruta al plugin embebido: drivers/win-x64/plugins primero, luego legacy."""
    candidates = (
        (bundled_plugins_dir(root), bundled_manifest_path(root)),
        (legacy_bundled_plugins_dir(root), legacy_bundled_plugins_dir(root) / "manifest.json"),
    )
    for plugin_dir, manifest_path in candidates:
        dll = plugin_dir / PLUGIN_DLL_NAME
        if not dll.is_file():
            continue
        try:
            if dll.stat().st_size < _MIN_PLUGIN_BYTES:
                continue
        except OSError:
            continue
        manifest = _load_manifest_file(manifest_path) if validate else None
        if validate and not _validate_plugin_against_manifest(dll, manifest):
            continue
        return dll
    return None


def bundled_soapy_dll_dir(root: Path | None = None) -> Path | None:
    """Directorio con SoapySDR.dll embebido (Fase 3); None si no está staged."""
    soapy = bundled_soapy_dir(root)
    dll = soapy / "SoapySDR.dll"
    return soapy if dll.is_file() else None


def bundled_soapy_util(root: Path | None = None) -> Path | None:
    util = bundled_soapy_dir(root) / "SoapySDRUtil.exe"
    return util if util.is_file() else None
