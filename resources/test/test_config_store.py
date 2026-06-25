"""Tests de core/config_store.py.

Verifican la API publica (funciones ``patch_*`` y ``persist_band_profile``)
contra el contrato funcional con la implementacion ``tomllib + tomli_w``.

A partir de la migracion (item 53 del informe):

* El archivo TOML se reescribe tras un patch con la representacion canonica
  del escritor TOML.
* Los valores actualizados aparecen en la seccion correcta.
* Los comentarios en linea y la alineacion manual de espacios se PIERDEN
  (trade-off documentado; el archivo se normaliza).
* Las claves no especificadas en el patch mantienen su valor.
* ``patch_missing_file_is_noop`` sigue siendo valido: si el archivo no existe,
  no se crea ni se lanza.

Refs:
- .mavis/plans/deliverables/final_report.md §Fase 3 item 53
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from core.config_store import (
    patch_device_section,
    patch_display_section,
    patch_dsp_section,
    patch_app_section,
    persist_band_profile,
)


def _write_toml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "defaults.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _parse(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


SAMPLE_TOML = """\
[device]
driver       = "auto"      # driver hint
sample_rate  = 500_000
center_freq  = 100_600_000
gain         = 30.0

[dsp]
volume       = 75.0
demod_mode   = "nbfm"
squelch_enabled  = false
wbfm_bandwidth = 147_540

[display]
waterfall_auto_level = true
display_level_mode = "per_column"
freq_span_mhz = 0.5

[app]
active_band_profile = ""
"""


def test_patch_device_rewrites_with_canonical_format(tmp_path: Path):
    """Tras un patch, el archivo se normaliza (sin comentarios, formato canonico)."""
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_device_section(str(path), driver="sdrplay", gain=42.0)
    text = path.read_text(encoding="utf-8")
    # Comentario en linea se pierde (trade-off conocido)
    assert "# driver hint" not in text
    # Valores actualizados presentes
    assert 'driver = "sdrplay"' in text
    assert "gain = 42.0" in text
    # Claves no modificadas preservan su valor
    data = _parse(path)
    assert data["device"]["sample_rate"] == 500_000


def test_patch_device_int_values_normalized(tmp_path: Path):
    """Los enteros se escriben sin separadores (tomli_w canónico)."""
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_device_section(str(path), sample_rate=2_048_000, center_freq=97_780_487)
    data = _parse(path)
    # El valor semántico se mantiene aunque el formato cambie
    assert data["device"]["sample_rate"] == 2_048_000
    assert data["device"]["center_freq"] == 97_780_487
    text = path.read_text(encoding="utf-8")
    # Formato canónico: sin underscores, espacios simples
    assert "sample_rate = 2048000" in text


def test_patch_dsp_bool_and_int(tmp_path: Path):
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_dsp_section(
        str(path),
        squelch_enabled=True,
        wbfm_bandwidth=80_000,
        volume=50.0,
    )
    data = _parse(path)
    assert data["dsp"]["squelch_enabled"] is True
    assert data["dsp"]["wbfm_bandwidth"] == 80_000
    assert data["dsp"]["volume"] == 50.0


def test_patch_display_section(tmp_path: Path):
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_display_section(str(path), waterfall_auto_level=False)
    data = _parse(path)
    assert data["display"]["waterfall_auto_level"] is False


def test_patch_missing_key_creates_section_with_value(tmp_path: Path):
    """Con tomllib+tomli_w, patch añade claves que no existían (no preserva ausencia).

    Antes (regex patcher) las claves ausentes se ignoraban.
    Ahora se añaden al dict. Este test verifica el nuevo comportamiento.
    """
    path = _write_toml(tmp_path, "[device]\ndriver = \"auto\"\n")
    patch_device_section(str(path), gain=99.0)
    data = _parse(path)
    # Nueva semántica: gain se añade aunque no existía
    assert data["device"]["gain"] == 99.0
    assert data["device"]["driver"] == "auto"


def test_patch_missing_file_is_noop(tmp_path: Path):
    missing = tmp_path / "missing.toml"
    # No debe lanzar
    patch_device_section(str(missing), driver="rtlsdr")
    # Y no debe crear el archivo
    assert not missing.is_file()


def test_persist_band_profile_writes_local_not_defaults(tmp_path: Path):
    defaults = _write_toml(tmp_path, SAMPLE_TOML)
    (tmp_path / "local.toml.example").write_text(SAMPLE_TOML, encoding="utf-8")
    profile = {
        "device": {"sample_rate": 2_048_000, "center_freq": 97_780_487, "gain": 40.0},
        "dsp": {"demod_mode": "wbfm", "volume": 80.0, "wbfm_bandwidth": 180_000},
        "display": {"display_level_mode": "per_column", "freq_span_mhz": 2.0},
    }
    persist_band_profile(str(defaults), "fm_broadcast", profile)
    # defaults.toml NO debe modificarse
    defaults_data = _parse(defaults)
    assert defaults_data["app"]["active_band_profile"] == ""
    # local.toml debe contener los nuevos valores
    local_path = tmp_path / "local.toml"
    assert local_path.is_file()
    local_data = _parse(local_path)
    assert local_data["app"]["active_band_profile"] == "fm_broadcast"
    assert local_data["device"]["sample_rate"] == 2_048_000
    assert local_data["dsp"]["demod_mode"] == "wbfm"
    assert local_data["dsp"]["wbfm_bandwidth"] == 180_000
    assert local_data["display"]["freq_span_mhz"] == 2.0


def test_patch_app_section_creates_section(tmp_path: Path):
    """patch_app_section crea [app] si no existía."""
    path = _write_toml(tmp_path, "[device]\ndriver = \"auto\"\n")
    patch_app_section(str(path), active_band_profile="airband")
    data = _parse(path)
    assert "app" in data
    assert data["app"]["active_band_profile"] == "airband"


def test_patch_dsp_preserves_other_keys(tmp_path: Path):
    """patch_dsp_section NO debe borrar claves no mencionadas."""
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_dsp_section(str(path), volume=99.0)
    data = _parse(path)
    # Claves no tocadas se mantienen
    assert data["dsp"]["demod_mode"] == "nbfm"
    assert data["dsp"]["squelch_enabled"] is False
    assert data["dsp"]["wbfm_bandwidth"] == 147_540
    # Clave actualizada
    assert data["dsp"]["volume"] == 99.0