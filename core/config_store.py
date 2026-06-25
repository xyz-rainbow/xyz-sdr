"""
xyz-sdr | core/config_store.py
Persistencia parcial de ajustes en el archivo TOML de configuración.

Implementación: round-trip con ``tomllib`` (lectura) + ``tomli_w`` (escritura).
Trade-off documentado (informe, item 53): se PIERDE la preservación de
comentarios en línea y de la alineación manual de espacios. El archivo
se reescribe con la representación canónica del escritor TOML.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.9/3.10 path
    import tomli as tomllib

import tomli_w


def user_config_path(defaults_path: str) -> str:
    """Ruta config/local.toml (preferencias de usuario, gitignored)."""
    return str(Path(defaults_path).parent / "local.toml")


def ensure_user_config(defaults_path: str) -> str:
    """Crea local.toml desde el ejemplo si no existe."""
    local = Path(user_config_path(defaults_path))
    if local.is_file():
        return str(local)
    local.parent.mkdir(parents=True, exist_ok=True)
    example = local.parent / "local.toml.example"
    if example.is_file():
        local.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        local.write_text(
            '# xyz-sdr user preferences\n\n[app]\nactive_band_profile = ""\n',
            encoding="utf-8",
        )
    return str(local)


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _write_toml(path: Path, data: dict[str, Any]) -> None:
    with path.open("wb") as handle:
        tomli_w.dump(data, handle)


def _ensure_section(data: dict[str, Any], section: str) -> dict[str, Any]:
    bucket = data.get(section)
    if not isinstance(bucket, dict):
        bucket = {}
        data[section] = bucket
    return bucket


def _apply_updates(section: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if value is not None:
            section[key] = value


def _patch_section(path: str, section: str, updates: dict[str, Any]) -> None:
    """Lee TOML, aplica ``updates`` en la sección indicada y reescribe."""
    config_path = Path(path)
    if not config_path.is_file():
        logger.warning("Config no encontrada: %s", path)
        return

    try:
        data = _read_toml(config_path)
    except Exception as exc:
        logger.error("No se pudo leer %s: %s", path, exc)
        return

    bucket = _ensure_section(data, section)
    _apply_updates(bucket, updates)

    try:
        _write_toml(config_path, data)
    except Exception as exc:
        logger.error("No se pudo escribir %s: %s", path, exc)
        return

    logger.info("Config %s actualizada: %s", section, path)


def patch_device_section(
    path: str,
    *,
    driver: str | None = None,
    sample_rate: float | None = None,
    center_freq: float | None = None,
    gain: float | None = None,
) -> None:
    """Actualiza valores en la sección [device] del archivo TOML."""
    updates = {
        "driver": driver,
        "sample_rate": int(sample_rate) if sample_rate is not None else None,
        "center_freq": int(center_freq) if center_freq is not None else None,
        "gain": gain,
    }
    _patch_section(path, "device", updates)


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
    _patch_section(path, "dsp", updates)


def patch_display_section(
    path: str,
    *,
    waterfall_auto_level: bool | None = None,
    display_level_mode: str | None = None,
    freq_span_mhz: float | None = None,
) -> None:
    """Actualiza valores en la sección [display] del archivo TOML."""
    updates = {
        "waterfall_auto_level": waterfall_auto_level,
        "display_level_mode": display_level_mode,
        "freq_span_mhz": freq_span_mhz,
    }
    _patch_section(path, "display", updates)


def patch_recorder_section(
    path: str,
    *,
    record_iq: bool | None = None,
    record_audio: bool | None = None,
) -> None:
    """Actualiza valores en la sección [recorder] del archivo TOML."""
    updates = {
        "record_iq": record_iq,
        "record_audio": record_audio,
    }
    _patch_section(path, "recorder", updates)


def patch_scanner_section(
    path: str,
    *,
    freq_start: float | None = None,
    freq_end: float | None = None,
    freq_step: float | None = None,
    dwell_ms: float | None = None,
    min_snr_db: float | None = None,
    pause_on_signal: bool | None = None,
    pause_resume_snr_db: float | None = None,
) -> None:
    """Actualiza valores en la sección [scanner] del archivo TOML."""
    updates = {
        "freq_start": int(freq_start) if freq_start is not None else None,
        "freq_end": int(freq_end) if freq_end is not None else None,
        "freq_step": int(freq_step) if freq_step is not None else None,
        "dwell_ms": int(dwell_ms) if dwell_ms is not None else None,
        "min_snr_db": min_snr_db,
        "pause_on_signal": pause_on_signal,
        "pause_resume_snr_db": pause_resume_snr_db,
    }
    _patch_section(path, "scanner", updates)


def patch_app_section(
    path: str,
    *,
    active_band_profile: str | None = None,
) -> None:
    """Actualiza la sección [app] (crea la sección si falta)."""
    if active_band_profile is None:
        return
    config_path = Path(path)
    if not config_path.is_file():
        logger.warning("Config no encontrada: %s", path)
        return

    try:
        data = _read_toml(config_path)
    except Exception as exc:
        logger.error("No se pudo leer %s: %s", path, exc)
        return

    bucket = _ensure_section(data, "app")
    bucket["active_band_profile"] = active_band_profile

    try:
        _write_toml(config_path, data)
    except Exception as exc:
        logger.error("No se pudo escribir %s: %s", path, exc)
        return

    logger.info("Config app actualizada: %s", path)


def persist_band_profile(path: str, profile_id: str, profile: dict[str, Any]) -> None:
    """Persiste un perfil de banda en config/local.toml (no modifica defaults.toml)."""
    local_path = ensure_user_config(path)
    dev = profile.get("device", {}) if isinstance(profile.get("device"), dict) else {}
    dsp = profile.get("dsp", {}) if isinstance(profile.get("dsp"), dict) else {}
    display = profile.get("display", {}) if isinstance(profile.get("display"), dict) else {}

    patch_device_section(
        local_path,
        sample_rate=float(dev["sample_rate"]) if "sample_rate" in dev else None,
        center_freq=float(dev["center_freq"]) if "center_freq" in dev else None,
        gain=float(dev["gain"]) if "gain" in dev else None,
    )
    patch_dsp_section(
        local_path,
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
        local_path,
        display_level_mode=str(display["display_level_mode"])
        if "display_level_mode" in display
        else None,
        freq_span_mhz=float(display["freq_span_mhz"]) if "freq_span_mhz" in display else None,
    )
    patch_app_section(local_path, active_band_profile=profile_id)