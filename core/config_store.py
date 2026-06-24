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
    fm_agc_enabled: bool | None = None,
    demod_mode: str | None = None,
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
        "fm_agc_enabled": fm_agc_enabled,
        "demod_mode": demod_mode,
    }

    for key, value in updates.items():
        if value is not None:
            text = _patch_key(text, key, value)

    config_path.write_text(text, encoding="utf-8")
    logger.info("Config DSP actualizada: %s", path)


def patch_display_section(
    path: str,
    *,
    waterfall_auto_level: bool | None = None,
    display_level_mode: str | None = None,
    freq_span_mhz: float | None = None,
) -> None:
    """Actualiza valores en la sección [display] del archivo TOML."""
    config_path = Path(path)
    if not config_path.is_file():
        logger.warning("Config no encontrada: %s", path)
        return

    text = config_path.read_text(encoding="utf-8")
    updates = {
        "waterfall_auto_level": waterfall_auto_level,
        "display_level_mode": display_level_mode,
        "freq_span_mhz": freq_span_mhz,
    }

    for key, value in updates.items():
        if value is not None:
            text = _patch_key(text, key, value)

    config_path.write_text(text, encoding="utf-8")
    logger.info("Config display actualizada: %s", path)


def _insert_or_patch_key(text: str, key: str, value: Any) -> str:
    """Actualiza una clave única o la añade al final si no existe."""
    patched = _patch_key(text, key, value)
    if patched != text:
        return patched
    return text.rstrip() + f"\n{key} = {_format_toml_value(value)}\n"


def patch_app_section(
    path: str,
    *,
    active_band_profile: str | None = None,
) -> None:
    """Actualiza la sección [app] (crea claves si faltan)."""
    config_path = Path(path)
    if not config_path.is_file():
        logger.warning("Config no encontrada: %s", path)
        return

    text = config_path.read_text(encoding="utf-8")
    if active_band_profile is not None:
        if "[app]" not in text:
            text = text.rstrip() + (
                f'\n\n[app]\nactive_band_profile = {_format_toml_value(active_band_profile)}\n'
            )
        else:
            text = _insert_or_patch_key(text, "active_band_profile", active_band_profile)

    config_path.write_text(text, encoding="utf-8")
    logger.info("Config app actualizada: %s", path)


def persist_band_profile(path: str, profile_id: str, profile: dict[str, Any]) -> None:
    """Persiste un perfil de banda en defaults.toml (device, dsp, display, [app])."""
    dev = profile.get("device", {}) if isinstance(profile.get("device"), dict) else {}
    dsp = profile.get("dsp", {}) if isinstance(profile.get("dsp"), dict) else {}
    display = profile.get("display", {}) if isinstance(profile.get("display"), dict) else {}

    patch_device_section(
        path,
        sample_rate=float(dev["sample_rate"]) if "sample_rate" in dev else None,
        center_freq=float(dev["center_freq"]) if "center_freq" in dev else None,
        gain=float(dev["gain"]) if "gain" in dev else None,
    )
    patch_dsp_section(
        path,
        demod_mode=str(dsp["demod_mode"]) if "demod_mode" in dsp else None,
        volume=float(dsp["volume"]) if "volume" in dsp else None,
        squelch_enabled=bool(dsp["squelch_enabled"]) if "squelch_enabled" in dsp else None,
        squelch_threshold=float(dsp["squelch_threshold"]) if "squelch_threshold" in dsp else None,
        wbfm_bandwidth=float(dsp["wbfm_bandwidth"]) if "wbfm_bandwidth" in dsp else None,
        nbfm_bandwidth=float(dsp["nbfm_bandwidth"]) if "nbfm_bandwidth" in dsp else None,
        am_bandwidth=float(dsp["am_bandwidth"]) if "am_bandwidth" in dsp else None,
        fm_deemphasis_us=float(dsp["fm_deemphasis_us"]) if "fm_deemphasis_us" in dsp else None,
        fm_agc_enabled=bool(dsp["fm_agc_enabled"]) if "fm_agc_enabled" in dsp else None,
    )
    patch_display_section(
        path,
        display_level_mode=str(display["display_level_mode"])
        if "display_level_mode" in display
        else None,
        freq_span_mhz=float(display["freq_span_mhz"]) if "freq_span_mhz" in display else None,
    )
    patch_app_section(path, active_band_profile=profile_id)
