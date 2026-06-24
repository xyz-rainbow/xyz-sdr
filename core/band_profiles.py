"""
xyz-sdr | core/band_profiles.py
Perfiles de configuración por banda de servicio (FM, aviación, HF, PMR…).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BANDS_DIR = Path(__file__).resolve().parent.parent / "config" / "bands"


def _load_toml(path: Path) -> dict[str, Any]:
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    with path.open("rb") as handle:
        return tomllib.load(handle)


def merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Fusión profunda de secciones TOML (override gana)."""
    merged = {key: value for key, value in base.items()}
    for key, value in override.items():
        if key == "meta":
            merged[key] = value
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            section = dict(merged[key])
            section.update(value)
            merged[key] = section
        else:
            merged[key] = value
    return merged


def bands_directory(root: Path | None = None) -> Path:
    if root is not None:
        return root / "config" / "bands"
    return _BANDS_DIR


def list_band_profiles(root: Path | None = None) -> list[tuple[str, str]]:
    """Devuelve (id, etiqueta) ordenados por nombre de archivo."""
    directory = bands_directory(root)
    if not directory.is_dir():
        return []

    profiles: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.toml")):
        profile_id = path.stem
        label = profile_id.replace("_", " ").title()
        try:
            data = _load_toml(path)
            meta = data.get("meta", {})
            if isinstance(meta, dict) and meta.get("label"):
                label = str(meta["label"])
        except Exception as exc:
            logger.debug("No se pudo leer meta de %s: %s", path, exc)
        profiles.append((profile_id, label))
    return profiles


def resolve_band_profile_path(name: str, root: Path | None = None) -> Path:
    """Resuelve id o ruta a un archivo TOML de perfil."""
    candidate = Path(name)
    if candidate.is_file():
        return candidate

    directory = bands_directory(root)
    for suffix in (".toml", ""):
        path = directory / f"{name}{suffix}"
        if path.is_file():
            return path

    available = ", ".join(item[0] for item in list_band_profiles(root))
    raise FileNotFoundError(
        f"Perfil de banda {name!r} no encontrado."
        + (f" Disponibles: {available}" if available else "")
    )


def load_band_profile(name: str, root: Path | None = None) -> dict[str, Any]:
    """Carga un perfil TOML de config/bands/."""
    path = resolve_band_profile_path(name, root=root)
    data = _load_toml(path)
    data.pop("meta", None)
    logger.info("Perfil de banda cargado: %s (%s)", name, path)
    return data
