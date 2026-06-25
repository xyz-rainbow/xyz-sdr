"""
xyz-sdr | setup/bundled_installers.py
Instaladores offline en resources/installers/ y rutas de respaldo locales.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Callable

from core.runtime_paths import project_root
from setup.windows_installers import SDRPLAY_INSTALLER_URL, download_file

SDRPLAY_INSTALLER_FILENAME = "SDRplay_RSP_API-Windows-3.15.exe"
BUNDLED_INSTALLERS_DIR = project_root() / "resources" / "installers" / "win-x64"
BUNDLED_SDRPLAY_MANIFEST = BUNDLED_INSTALLERS_DIR / "manifest.json"


def bundled_sdrplay_installer_path(*, verify_manifest: bool = True) -> Path | None:
    """Ruta al instalador embebido en resources/installers/win-x64/."""
    path = BUNDLED_INSTALLERS_DIR / SDRPLAY_INSTALLER_FILENAME
    if not path.is_file():
        return None
    if not verify_manifest:
        return path
    manifest = load_sdrplay_installer_manifest()
    if manifest is None:
        return path
    try:
        if path.stat().st_size != int(manifest.get("size_bytes", 0)):
            return None
        if manifest.get("sha256") and _sha256_file(path) != str(manifest["sha256"]).lower():
            return None
    except OSError:
        return None
    return path


def load_sdrplay_installer_manifest() -> dict | None:
    if not BUNDLED_SDRPLAY_MANIFEST.is_file():
        return None
    try:
        return json.loads(BUNDLED_SDRPLAY_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_sdrplay_installer_candidates() -> list[Path]:
    """Rutas locales opcionales (Downloads, U:\\, env) sin el bundle resources."""
    names = [SDRPLAY_INSTALLER_FILENAME, "SDRplay_RSP_API-Windows-3.15.1.exe"]
    candidates: list[Path] = []

    env_path = os.environ.get("XYZ_SDR_SDRPLAY_INSTALLER", "").strip()
    if env_path:
        candidates.append(Path(env_path))

    home = Path.home()
    for base in (home / "Downloads", Path(r"U:\Downloads"), Path(r"U:/Downloads")):
        for name in names:
            candidates.append(base / name)

    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        if not path.is_file():
            continue
        key = os.path.normcase(str(path.resolve()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def acquire_sdrplay_installer(
    temp_dir: str,
    *,
    lang: str = "es",
    on_message: Callable[[str], None] | None = None,
) -> str | None:
    """
    Resuelve el instalador SDRplay API: bundled → local → descarga URL.

    Returns:
        Ruta absoluta al .exe o None si no se pudo obtener.
    """
    say = on_message or (lambda _msg: None)

    verified = bundled_sdrplay_installer_path(verify_manifest=True)
    if verified is not None:
        say(f"  [OK] Instalador embebido (verificado): {verified}")
        return str(verified.resolve())

    for local in local_sdrplay_installer_candidates():
        say(f"  [OK] Instalador local: {local}")
        return str(local.resolve())

    raw_bundled = BUNDLED_INSTALLERS_DIR / SDRPLAY_INSTALLER_FILENAME
    if raw_bundled.is_file():
        say(f"  [OK] Instalador embebido: {raw_bundled}")
        return str(raw_bundled.resolve())

    dest = os.path.join(temp_dir, SDRPLAY_INSTALLER_FILENAME)
    say("  [>>] Descargando SDRplay API…")
    if download_file(SDRPLAY_INSTALLER_URL, dest, "SDRplay API", lang=lang, on_message=say):
        return dest

    say("  [XX] No se encontró instalador local ni descarga.")
    say(f"  [>>] Coloca {SDRPLAY_INSTALLER_FILENAME} en:")
    say(f"       {BUNDLED_INSTALLERS_DIR}")
    say("  [>>] O en Downloads, o define XYZ_SDR_SDRPLAY_INSTALLER=ruta\\al.exe")
    say(f"  [>>] URL: {SDRPLAY_INSTALLER_URL}")
    return None


def stage_sdrplay_installer(temp_dir: str) -> str | None:
    """Copia el instalador resuelto a temp_dir (útil para tests o instalación aislada)."""
    source = acquire_sdrplay_installer(temp_dir, on_message=lambda _m: None)
    if not source:
        return None
    if os.path.normcase(os.path.dirname(os.path.abspath(source))) == os.path.normcase(
        os.path.abspath(temp_dir)
    ):
        return source
    dest = os.path.join(temp_dir, SDRPLAY_INSTALLER_FILENAME)
    shutil.copy2(source, dest)
    return dest
