"""
xyz-sdr | core/bookmarks.py
Carga, guardado, exportación e importación de bookmarks de frecuencia.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

Bookmark = tuple[str, float, str]


def _load_toml(path: Path) -> dict:
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    with path.open("rb") as handle:
        return tomllib.load(handle)


def parse_bookmarks_data(data: dict) -> list[Bookmark]:
    bookmarks: list[Bookmark] = []
    for item in data.get("bookmarks", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "Favorito"))
        freq = float(item.get("freq_hz", 0.0))
        mode = str(item.get("mode", "wbfm"))
        bookmarks.append((name, freq, mode))
    return bookmarks


def save_bookmarks(path: Path, bookmarks: list[Bookmark]) -> None:
    """Escribe bookmarks en formato TOML [[bookmarks]]."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# xyz-sdr | bookmarks — favoritos de frecuencia", ""]
    for name, freq, mode in bookmarks:
        lines.extend(
            [
                "[[bookmarks]]",
                f'name = "{name}"',
                f"freq_hz = {int(freq)}",
                f'mode = "{mode}"',
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def load_bookmarks(path: Path, fallback: list[Bookmark]) -> list[Bookmark]:
    """Carga bookmarks desde TOML; si no existe, inicializa con fallback."""
    if not path.is_file():
        save_bookmarks(path, fallback)
        return list(fallback)
    try:
        data = _load_toml(path)
        bookmarks = parse_bookmarks_data(data)
        return bookmarks if bookmarks else list(fallback)
    except Exception as exc:
        logger.error("Error cargando bookmarks %s: %s", path, exc)
        return list(fallback)


def export_bookmarks(bookmarks: list[Bookmark], dest: Path) -> None:
    save_bookmarks(dest, bookmarks)


def import_bookmarks(src: Path, fallback: list[Bookmark]) -> list[Bookmark]:
    """Importa desde archivo; lanza FileNotFoundError si no existe."""
    if not src.is_file():
        raise FileNotFoundError(f"No se encontró: {src}")
    data = _load_toml(src)
    imported = parse_bookmarks_data(data)
    if not imported:
        return list(fallback)
    return imported


def merge_bookmarks(base: list[Bookmark], imported: list[Bookmark]) -> list[Bookmark]:
    """Fusiona listas deduplicando por frecuencia (±1 Hz) y modo."""
    merged = list(base)
    for name, freq, mode in imported:
        if any(abs(existing[1] - freq) < 1.0 and existing[2] == mode for existing in merged):
            continue
        merged.append((name, freq, mode))
    return merged
