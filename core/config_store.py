"""
xyz-sdr | core/config_store.py
Persistencia parcial de ajustes en el archivo TOML de configuración.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value:_}"
    if isinstance(value, float):
        if value.is_integer() and abs(value) >= 1000:
            return f"{int(value):_}"
        return repr(value)
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)


def _patch_key(text: str, key: str, value: Any) -> str:
    """Reemplaza una clave de primer nivel conservando comentarios al final de línea."""
    value_repr = _format_toml_value(value)
    pattern = rf'^({re.escape(key)}\s*=\s*)(.+)$'

    def _repl(match: re.Match[str]) -> str:
        tail = match.group(2)
        comment = ""
        if "#" in tail:
            comment = tail[tail.index("#") :]
        sep = "      " if comment else ""
        return f"{match.group(1)}{value_repr}{sep}{comment}"

    new_text, count = re.subn(pattern, _repl, text, count=1, flags=re.MULTILINE)
    if count == 0:
        logger.warning("No se encontró la clave %s en el TOML", key)
        return text
    return new_text


def patch_device_section(
    path: str,
    *,
    driver: str | None = None,
    sample_rate: float | None = None,
    center_freq: float | None = None,
    gain: float | None = None,
) -> None:
    """Actualiza valores en la sección [device] del archivo TOML."""
    config_path = Path(path)
    if not config_path.is_file():
        logger.warning("Config no encontrada: %s", path)
        return

    text = config_path.read_text(encoding="utf-8")
    updates = {
        "driver": driver,
        "sample_rate": int(sample_rate) if sample_rate is not None else None,
        "center_freq": int(center_freq) if center_freq is not None else None,
        "gain": gain,
    }

    for key, value in updates.items():
        if value is not None:
            text = _patch_key(text, key, value)

    config_path.write_text(text, encoding="utf-8")
    logger.info("Config actualizada: %s", path)


def patch_dsp_section(
    path: str,
    *,
    squelch_enabled: bool | None = None,
    squelch_threshold: float | None = None,
    squelch_hang_ms: float | None = None,
    volume: float | None = None,
    wbfm_bandwidth: float | None = None,
    nbfm_bandwidth: float | None = None,
    am_bandwidth: float | None = None,
    fm_deemphasis_us: float | None = None,
) -> None:
    """Actualiza valores en la sección [dsp] del archivo TOML."""
    config_path = Path(path)
    if not config_path.is_file():
        logger.warning("Config no encontrada: %s", path)
        return

    text = config_path.read_text(encoding="utf-8")
    updates = {
        "squelch_enabled": squelch_enabled,
        "squelch_threshold": int(squelch_threshold) if squelch_threshold is not None else None,
        "squelch_hang_ms": int(squelch_hang_ms) if squelch_hang_ms is not None else None,
        "volume": volume,
        "wbfm_bandwidth": int(wbfm_bandwidth) if wbfm_bandwidth is not None else None,
        "nbfm_bandwidth": int(nbfm_bandwidth) if nbfm_bandwidth is not None else None,
        "am_bandwidth": int(am_bandwidth) if am_bandwidth is not None else None,
        "fm_deemphasis_us": int(fm_deemphasis_us) if fm_deemphasis_us is not None else None,
    }

    for key, value in updates.items():
        if value is not None:
            text = _patch_key(text, key, value)

    config_path.write_text(text, encoding="utf-8")
    logger.info("Config DSP actualizada: %s", path)
